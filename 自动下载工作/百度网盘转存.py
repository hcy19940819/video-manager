# -*- coding: utf-8 -*-
"""
百度网盘自动转存工具
支持：断点续传、进度显示、关闭窗口即停止、智能状态检测、异常记录
"""

import os
import sys
import time
import json
import signal
from pathlib import Path
from datetime import datetime

import pyperclip
import pyautogui
import psutil

from progress import (
    load_progress, save_progress, clear_progress,
    get_pending_links, print_progress_bar
)
from window_inspector import wait_for_status, detect_baidu_status

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5

BASE_DIR = Path(__file__).parent
BAIDU_LNK = r'C:/Users/HCY/Desktop/百度网盘.lnk'
COORDS_FILE = BASE_DIR / 'baidu_coords.json'
RUNTIME_LOG = []
STOP_FLAG = False
CURRENT_LOG_FILE = None

# 异常记录配置
EXCEPTION_DIR = BASE_DIR / '异常文件夹'


def signal_handler(sig, frame):
    global STOP_FLAG
    STOP_FLAG = True
    print('\n\n[用户中断] 正在保存进度并退出...')


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def log(msg, log_type='INFO'):
    """
    记录日志
    log_type: INFO/SUCCESS/ERROR/WARN/EXCEPTION
    """
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = '[{0}] [{1}] {2}'.format(timestamp, log_type, msg)
    RUNTIME_LOG.append(line)
    print(line)
    
    # 实时写入日志文件
    global CURRENT_LOG_FILE
    if CURRENT_LOG_FILE:
        with open(CURRENT_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def load_coords():
    if COORDS_FILE.exists():
        with open(COORDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def is_baidu_running():
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name'] or ''
            if 'baidu' in name.lower() or '百度' in name or 'BaiduNetdisk' in name:
                return True
        except:
            pass
    return False


def start_baidu():
    if is_baidu_running():
        log('百度网盘已在运行', 'INFO')
        return True
    
    if os.path.exists(BAIDU_LNK):
        log('启动百度网盘...', 'INFO')
        os.startfile(BAIDU_LNK)
        time.sleep(10)
        return True
    else:
        log('未找到快捷方式', 'ERROR')
        return False


def click_close_btn(coords):
    """点击关闭按钮"""
    close_btn = coords.get('close_btn')
    if close_btn:
        pyautogui.click(close_btn['x'], close_btn['y'])
        time.sleep(0.5)


def record_exception(url: str, exception_type: str, folder_name: str, source_file: str = 'baidu_pan_links.txt'):
    """
    记录异常链接
    exception_type: wrong_code/captcha/need_login/limit/file_deleted
    """
    # 链接失效不需要记录
    if exception_type == 'link_invalid':
        log('链接失效，跳过记录: {0}'.format(url[:50]), 'WARN')
        return
    
    # 创建异常文件夹
    exception_folder = EXCEPTION_DIR / folder_name
    exception_folder.mkdir(parents=True, exist_ok=True)
    
    # 异常类型映射到文件名
    exception_files = {
        'wrong_code': 'baidu_wrong_code.txt',
        'captcha': 'baidu_captcha.txt',
        'need_login': 'baidu_need_login.txt',
        'limit': 'baidu_limit.txt',
        'file_deleted': 'baidu_file_deleted.txt',
    }
    
    filename = exception_files.get(exception_type, 'baidu_other.txt')
    exception_file = exception_folder / filename
    
    # 追加记录
    with open(exception_file, 'a', encoding='utf-8') as f:
        f.write('{0}  # 来源: {1}\n'.format(url, source_file))
    
    log('已记录异常 [{0}]: {1}'.format(exception_type, url[:50]), 'EXCEPTION')


def process_link(url, coords, folder_name, retry_links):
    """
    处理单个链接，智能检测状态
    
    状态规则（同迅雷）：
    1. 失效/无效链接 → 关闭，不计异常，不复开
    2. 提取码错误 → 关闭，记异常，不复开
    3. 链接错误 → 关闭，记异常，不复开
    4. 需要登录/操作频繁 → 致命错误，立即停止
    5. 加载未完成 → 刷新等待10s，最多3次，失败则记异常，需复开
    
    返回: (是否成功, 是否致命错误, 是否需复开)
    """
    DETECT_TIMEOUT = 10  # 加载超时10秒
    MAX_RETRY = 3  # 最多刷新3次
    
    try:
        # 1. 复制链接
        pyperclip.copy(url)
        time.sleep(0.5)
        
        # 2. 粘贴链接
        pyautogui.hotkey('ctrl', 'v')
        
        # 3. 等待页面加载，检测状态（最多5秒）
        log('等待页面加载...', 'INFO')
        result = wait_for_status('baidu', ['百度网盘', 'Baidu'], timeout=5, interval=0.3)
        
        if result['found'] and result['status']['status'] == 'error':
            error_type = result['status']['type']
            
            # 致命错误：需要登录/操作频繁 → 立即停止
            if error_type in ['need_login', 'limit']:
                log('致命错误 [{0}]：{1}'.format(error_type, result['status']['message']), 'ERROR')
                record_exception(url, error_type, folder_name)
                return False, True, False  # 失败，致命错误，不复开
            
            # 失效/无效链接 → 关闭，不计异常，不复开
            if error_type == 'link_invalid':
                log('链接失效，跳过', 'WARN')
                click_close_btn(coords)
                return False, False, False
            
            # 其他错误（提取码错误等）→ 关闭，记异常，不复开
            log('错误 [{0}] {1}'.format(error_type, result['status']['message']), 'ERROR')
            record_exception(url, error_type, folder_name)
            click_close_btn(coords)
            return False, False, False
        
        # 4. 点击【转存】按钮
        log('点击转存...', 'INFO')
        save_btn = coords.get('save_btn')
        if save_btn:
            pyautogui.click(save_btn['x'], save_btn['y'])
        else:
            log('未找到转存按钮坐标', 'ERROR')
            return False, False, False
        
        # 5. 等待转存结果（10秒超时，可刷新3次）
        log('等待转存结果...', 'INFO')
        retry_count = 0
        start_time = time.time()
        
        while True:
            if STOP_FLAG:
                return False, False, False
            
            elapsed = time.time() - start_time
            status = detect_baidu_status()
            
            if status['status'] == 'success':
                log('转存成功', 'SUCCESS')
                click_close_btn(coords)
                return True, False, False
            
            elif status['status'] == 'error':
                error_type = status['type']
                
                # 致命错误
                if error_type in ['need_login', 'limit']:
                    log('致命错误 [{0}]'.format(error_type), 'ERROR')
                    record_exception(url, error_type, folder_name)
                    return False, True, False
                
                # 失效链接
                if error_type == 'link_invalid':
                    log('链接失效', 'WARN')
                    click_close_btn(coords)
                    return False, False, False
                
                # 其他错误
                log('错误 [{0}]'.format(error_type), 'ERROR')
                record_exception(url, error_type, folder_name)
                click_close_btn(coords)
                return False, False, False
            
            # 检查超时
            if elapsed > DETECT_TIMEOUT:
                retry_count += 1
                if retry_count <= MAX_RETRY:
                    log('加载超时，刷新重试 ({0}/{1})'.format(retry_count, MAX_RETRY), 'WARN')
                    pyautogui.press('f5')  # 刷新
                    time.sleep(2)
                    # 重新点击转存
                    if save_btn:
                        pyautogui.click(save_btn['x'], save_btn['y'])
                    start_time = time.time()
                else:
                    # 3次刷新失败，记异常，需复开
                    log('刷新3次仍失败，稍后复开', 'ERROR')
                    record_exception(url, 'load_timeout', folder_name)
                    click_close_btn(coords)
                    return False, False, True  # 失败，非致命，需复开
            
            time.sleep(0.5)
        
    except Exception as e:
        log('失败: {0}'.format(e), 'ERROR')
        return False, False, False


def find_latest_folder(base_dir):
    if not base_dir.exists():
        return None
    folders = [f for f in base_dir.iterdir() if f.is_dir()]
    if not folders:
        return None
    return max(folders, key=lambda x: x.name)


def load_pan_links(pan_type, folder):
    """加载网盘链接"""
    links = []
    for txt_file in folder.glob('*.txt'):
        with open(txt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            if pan_type == 'baidu' and 'pan.baidu.com' in line:
                links.append({'url': line, 'code': ''})
    return links


def main():
    global STOP_FLAG, CURRENT_LOG_FILE
    
    print('=' * 60)
    print('百度网盘自动转存')
    print('=' * 60)
    print()
    print('提示：关闭此窗口即可停止程序')
    print('异常记录：保存到 异常文件夹/<日期>/')
    print()
    
    coords = load_coords()
    if not coords:
        print('[错误] 未找到坐标，请先校准坐标')
        input('按 Enter 退出...')
        return
    
    # 加载链接
    stboy_dir = Path(r'D:/AI/AI_Tool/STboy_Auto/extracted_links')
    latest = find_latest_folder(stboy_dir)
    
    if not latest:
        print('[错误] 未找到链接文件夹')
        input('按 Enter 退出...')
        return
    
    folder_name = latest.name
    
    links_data = load_pan_links('baidu', latest)
    all_links = [d['url'] for d in links_data]
    
    if not all_links:
        print('[错误] 没有待处理的链接')
        input('按 Enter 退出...')
        return
    
    # 检查断点续传
    pending_links, is_resume, progress = get_pending_links('baidu', all_links, folder_name)
    
    if is_resume:
        completed_count = len(progress.get('completed', []))
        failed_count = len(progress.get('failed', []))
        print()
        print('发现未完成的任务！')
        print('  文件夹: {0}'.format(folder_name))
        print('  总计: {0}'.format(len(all_links)))
        print('  已完成: {0}'.format(completed_count))
        print('  失败: {0}'.format(failed_count))
        print('  待处理: {0}'.format(len(pending_links)))
        print()
        print('请选择：')
        print('  Y - 继续上次任务')
        print('  N - 取消，读取最新文件夹重新下载')
        print('  C - 取消，返回主菜单')
        choice = input('请输入 (Y/N/C): ').strip().upper()
        
        if choice == 'C':
            print('已取消')
            return
        elif choice == 'N':
            clear_progress('baidu')
            latest = find_latest_folder(stboy_dir)
            if not latest:
                print('[错误] 未找到链接文件夹')
                input('按 Enter 退出...')
                return
            folder_name = latest.name
            links_data = load_pan_links('baidu', latest)
            all_links = [d['url'] for d in links_data]
            pending_links = all_links
            completed = []
            failed = []
            print()
            print('已切换到最新文件夹: {0}'.format(folder_name))
        else:
            completed = progress.get('completed', [])
            failed = progress.get('failed', [])
    else:
        completed = []
        failed = []
    
    total = len(all_links)
    remaining = len(pending_links)
    
    print()
    print('准备转存 {0} 个链接'.format(remaining))
    print()
    
    # 初始化日志文件
    log_dir = BASE_DIR / 'logs'
    log_dir.mkdir(exist_ok=True)
    CURRENT_LOG_FILE = log_dir / 'baidu_{0}_{1}.log'.format(folder_name, datetime.now().strftime('%H%M%S'))
    
    # 写入日志头
    with open(CURRENT_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('=' * 60 + '\n')
        f.write('百度网盘转存日志\n')
        f.write('文件夹: {0}\n'.format(folder_name))
        f.write('开始时间: {0}\n'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        f.write('总计链接: {0}\n'.format(total))
        f.write('=' * 60 + '\n\n')
    
    log('日志文件: {0}'.format(CURRENT_LOG_FILE), 'INFO')
    print()
    
    if not start_baidu():
        print('[错误] 无法启动百度网盘')
        input('按 Enter 退出...')
        return
    
    print()
    print('5秒后开始，请切换到百度网盘窗口...')
    for i in range(5, 0, -1):
        print('\r倒计时: {0} 秒'.format(i), end='', flush=True)
        time.sleep(1)
    print('\r开始转存！                ')
    print()
    print('=' * 60)
    
    # 主循环
    processed = 0
    retry_links = []  # 需复开的链接（加载超时）
    fatal_error = False
    normal_phase_done = False
    
    i = 0
    while i < len(pending_links) or retry_links:
        if STOP_FLAG or fatal_error:
            break
        
        # 阶段1：正常流程
        if not normal_phase_done and i < len(pending_links):
            url = pending_links[i]['url'] if isinstance(pending_links[i], dict) else pending_links[i]
            i += 1
        
        # 阶段2：正常流程完成后，处理复开链接
        elif normal_phase_done and retry_links:
            url = retry_links.pop(0)
            log('复开异常链接: {0}'.format(url[:50]), 'WARN')
        
        # 阶段切换
        elif not normal_phase_done and i >= len(pending_links):
            normal_phase_done = True
            if retry_links:
                log('正常链接处理完毕，待复开异常链接: {0} 个'.format(len(retry_links)))
                continue
            else:
                break
        else:
            break
        
        current_num = len(completed) + len(failed) + 1
        
        print()
        print('[{0}/{1}] {2}'.format(current_num, total, url[:55]))
        log('处理 [{0}/{1}] {2}'.format(current_num, total, url[:50]), 'INFO')
        
        success, is_fatal, need_retry = process_link(url, coords, folder_name, retry_links)
        
        if is_fatal:
            log('遇到致命错误，保存进度并退出...', 'ERROR')
            fatal_error = True
            break
        
        if success:
            completed.append(url)
        elif need_retry:
            retry_links.append(url)
            log('标记为稍后复开', 'WARN')
        else:
            failed.append(url)
        
        processed += 1
        
        # 保存进度
        save_progress('baidu', folder_name, completed, failed, total)
        
        # 显示总进度
        current_done = len(completed) + len(failed)
        print_progress_bar(current_done, total, prefix='总进度')
        
        if not STOP_FLAG:
            time.sleep(2)
    
    # 结果
    print()
    print('=' * 60)
    log('转存结束！', 'INFO')
    log('总计: {0}'.format(total), 'INFO')
    log('成功: {0}'.format(len(completed)), 'SUCCESS')
    log('失败: {0}'.format(len(failed)), 'WARN')
    log('本次处理: {0}'.format(processed), 'INFO')
    
    # 写入日志尾
    if CURRENT_LOG_FILE:
        with open(CURRENT_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write('\n' + '=' * 60 + '\n')
            f.write('转存结束\n')
            f.write('总计: {0}\n'.format(total))
            f.write('成功: {0}\n'.format(len(completed)))
            f.write('失败: {0}\n'.format(len(failed)))
            f.write('结束时间: {0}\n'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            f.write('=' * 60 + '\n')
    
    # 显示异常记录位置
    exception_folder = EXCEPTION_DIR / folder_name
    if exception_folder.exists():
        print()
        print('异常记录位置: {0}'.format(exception_folder))
        for f in exception_folder.glob('*.txt'):
            content = f.read_text(encoding='utf-8').strip()
            count = len(content.split('\n')) if content else 0
            print('  - {0}: {1} 条'.format(f.name, count))
            log('异常文件 {0}: {1} 条'.format(f.name, count), 'EXCEPTION')
    
    # 统计（包括复开的）
    total_done = len(completed) + len(failed)
    
    if fatal_error:
        print()
        print('[ERROR] 遇到致命错误，任务已暂停')
        print('        处理登录或风控问题后，可从断点继续')
        log('致命错误暂停，进度已保存', 'ERROR')
    elif total_done >= total and not retry_links:
        print()
        print('[OK] 全部完成！清除进度记录...')
        log('全部完成！清除进度记录', 'SUCCESS')
        clear_progress('baidu')
    else:
        print()
        print('[WARN] 任务未完成，进度已保存，下次可继续')
        log('任务未完成，进度已保存', 'WARN')
    
    print('=' * 60)
    print()
    input('按 Enter 退出...')


if __name__ == '__main__':
    main()
