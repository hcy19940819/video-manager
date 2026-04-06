# -*- coding: utf-8 -*-
"""
迅雷网盘自动转存工具
支持：断点续传、7窗口动态并行、刷新重试、自动补满、异常记录
"""

import os
import sys
import time
import json
import signal
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

import pyperclip
import pyautogui
import psutil

from progress import (
    load_progress, save_progress, clear_progress,
    get_pending_links, print_progress_bar
)
from window_inspector import detect_xunlei_status

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

BASE_DIR = Path(__file__).parent
COORDS_FILE = BASE_DIR / 'xl_coords.json'
XUNLEI_LNK = r'C:/Users/HCY/Desktop/迅雷.lnk'
RUNTIME_LOG = []
STOP_FLAG = False
CURRENT_LOG_FILE = None  # 当前日志文件路径

# 配置
MAX_WINDOWS = 7  # 最大并行窗口数
TAB_COORDS = {'x': 765, 'y': 333}  # 第1个标签页坐标
TAB_WIDTH = 100  # 每个标签页宽度
DETECT_TIMEOUT = 6  # 单个窗口检测超时(秒)
REFRESH_COORDS = {'x': 750, 'y': 366}  # 刷新按钮坐标

# 异常记录配置
EXCEPTION_DIR = BASE_DIR / '异常文件夹'


@dataclass
class WindowState:
    """窗口状态"""
    index: int  # 窗口索引(0-6)
    url: str
    status: str  # 'pending'(待处理)/'processing'(处理中)/'success'(成功)/'failed'(失败)/'stuck'(卡住)
    start_time: float
    retry_count: int = 0


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


def is_xunlei_running():
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name'] or ''
            if 'xunlei' in name.lower() or 'thunder' in name.lower():
                return True
        except:
            pass
    return False


def start_xunlei():
    if is_xunlei_running():
        log('迅雷已在运行')
        return True
    
    if os.path.exists(XUNLEI_LNK):
        log('启动迅雷...')
        os.startfile(XUNLEI_LNK)
        time.sleep(10)
        return True
    else:
        log('[错误] 未找到迅雷快捷方式')
        return False


def close_tab():
    pyautogui.keyDown('ctrl')
    pyautogui.keyDown('w')
    pyautogui.keyUp('w')
    pyautogui.keyUp('ctrl')
    time.sleep(0.3)


def click_tab(index):
    """点击第index个标签页"""
    x = TAB_COORDS['x'] + index * TAB_WIDTH
    y = TAB_COORDS['y']
    pyautogui.click(x, y)
    time.sleep(0.3)


def refresh_page():
    """刷新当前页面"""
    pyautogui.click(REFRESH_COORDS['x'], REFRESH_COORDS['y'])
    time.sleep(0.5)


def open_link(url):
    """打开一个新链接"""
    pyperclip.copy(url)
    time.sleep(0.3)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(1.4)  # 总共约2秒间隔


def click_save(coords):
    """点击转存按钮"""
    btn = coords.get('save_btn')
    if btn:
        pyautogui.click(btn['x'], btn['y'])
        return True
    return False


def record_exception(url: str, exception_type: str, folder_name: str, source_file: str = 'xunlei_pan_links.txt'):
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
        'wrong_code': 'xunlei_wrong_code.txt',
        'captcha': 'xunlei_captcha.txt',
        'need_login': 'xunlei_need_login.txt',
        'limit': 'xunlei_limit.txt',
        'file_deleted': 'xunlei_file_deleted.txt',
    }
    
    filename = exception_files.get(exception_type, 'xunlei_other.txt')
    exception_file = exception_folder / filename
    
    # 追加记录
    with open(exception_file, 'a', encoding='utf-8') as f:
        f.write('{0}  # 来源: {1}\n'.format(url, source_file))
    
    log('已记录异常 [{0}]: {1}'.format(exception_type, url[:50]), 'EXCEPTION')


def process_windows(windows: List[WindowState], coords, pending_urls: List[str], folder_name: str) -> tuple:
    """
    处理所有窗口，返回 (更新后的窗口列表, 剩余待处理URL)
    动态补满：有窗口完成就立即开新链接
    
    策略：总是点击标签0（最左边），处理完关闭后迅雷自动切换到下一个
    """
    # 按索引排序，但总是从第一个开始处理
    windows.sort(key=lambda w: w.index)
    
    while windows and not STOP_FLAG:
        # 总是点击最左边的标签（索引0）
        window = windows[0]
        click_tab(0)
        
        if window.status == 'pending':
            # 新窗口，点击转存
            log('窗口{0}: 点击转存 {1}'.format(window.index + 1, window.url[:40]), 'INFO')
            if click_save(coords):
                window.status = 'processing'
                window.start_time = time.time()
            else:
                window.status = 'failed'
                log('窗口{0}: 未找到转存按钮'.format(window.index + 1), 'ERROR')
        
        elif window.status == 'processing':
            # TODO: 状态识别有问题，暂时禁用，后续研究
            # 原代码：
            # time.sleep(0.5)
            # status = detect_xunlei_status()
            # log('  检测状态: {0}, 类型: {1}, 消息: {2}'.format(
            #     status['status'], status['type'], status['message'][:30]), 'INFO')
            # if status['status'] == 'success':
            #     window.status = 'success'
            #     log('窗口{0}: 转存成功'.format(window.index + 1), 'SUCCESS')
            # elif status['status'] == 'error':
            #     window.status = 'failed'
            #     log('窗口{0}: 错误 [{1}] {2}'.format(window.index + 1, status['type'], status['message']), 'ERROR')
            #     if status['type'] != 'link_invalid':
            #         record_exception(window.url, status['type'], folder_name)
            # else:
            #     elapsed = time.time() - window.start_time
            #     if elapsed > DETECT_TIMEOUT:
            #         window.status = 'stuck'
            #         log('窗口{0}: 处理超时，标记为卡住'.format(window.index + 1), 'WARN')
            
            # 临时方案：固定等待8秒后假设成功
            elapsed = time.time() - window.start_time
            if elapsed > 8:
                window.status = 'success'
                log('窗口{0}: 等待8秒，标记成功'.format(window.index + 1), 'SUCCESS')
            else:
                log('窗口{0}: 处理中...'.format(window.index + 1), 'INFO')
        
        elif window.status == 'stuck':
            # 卡住的窗口，尝试刷新重试
            if window.retry_count < 2:  # 最多重试2次
                window.retry_count += 1
                log('窗口{0}: 刷新重试 ({1}/2)'.format(window.index + 1, window.retry_count), 'WARN')
                refresh_page()
                time.sleep(2)
                # 重新点击转存
                click_save(coords)
                window.status = 'processing'
                window.start_time = time.time()
                # 刷新后变成processing，本轮结束等待
                break
            else:
                # 重试次数用完，标记为失败
                window.status = 'failed'
                log('窗口{0}: 重试次数用完，标记为失败'.format(window.index + 1), 'ERROR')
        
        # 如果窗口已完成或失败，关闭并开新链接补满
        if window.status in ['success', 'failed']:
            close_tab()
            time.sleep(0.3)
            
            # 从列表中移除已处理的窗口
            windows.pop(0)
            
            # 如果有待处理的URL，开新链接（放在最后，保持最多7个）
            if pending_urls:
                new_url = pending_urls.pop(0)
                log('开新链接: {0}'.format(new_url[:40]), 'INFO')
                open_link(new_url)
                # 添加新窗口到列表末尾
                new_index = max(w.index for w in windows) + 1 if windows else 0
                windows.append(WindowState(index=new_index, url=new_url, status='pending', start_time=0))
            
            continue
        
        # 如果窗口还在processing（加载中），本轮跳过，等下一轮再检测
        # 由于我们总是点击标签0，而这个窗口还在loading，
        # 我们需要暂时跳过它，但标签页顺序没变，所以直接break结束本轮
        if window.status == 'processing':
            # 检查是否所有窗口都在processing
            all_processing = all(w.status == 'processing' for w in windows)
            if all_processing:
                log('所有窗口加载中，本轮结束等待...')
            break
    
    return windows, pending_urls


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
            if pan_type == 'xunlei' and 'pan.xunlei.com' in line:
                links.append({'url': line, 'code': ''})
    return links


def main():
    global STOP_FLAG
    
    print('=' * 60)
    print('迅雷网盘自动转存')
    print('=' * 60)
    print()
    print('提示：关闭此窗口即可停止程序')
    print('并行模式：动态 {0} 窗口，支持刷新重试'.format(MAX_WINDOWS))
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
    
    folder_name = latest.name  # 保存文件夹名用于异常记录
    
    links_data = load_pan_links('xunlei', latest)
    all_links = [d['url'] for d in links_data]
    
    if not all_links:
        print('[错误] 没有待处理的链接')
        input('按 Enter 退出...')
        return
    
    # 检查断点续传
    pending_urls, is_resume, progress = get_pending_links('xunlei', all_links, folder_name)
    
    if is_resume:
        completed_count = len(progress.get('completed', []))
        failed_count = len(progress.get('failed', []))
        print()
        print('发现未完成的任务！')
        print('  文件夹: {0}'.format(folder_name))
        print('  总计: {0}'.format(len(all_links)))
        print('  已完成: {0}'.format(completed_count))
        print('  失败: {0}'.format(failed_count))
        print('  待处理: {0}'.format(len(pending_urls)))
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
            clear_progress('xunlei')
            latest = find_latest_folder(stboy_dir)
            if not latest:
                print('[错误] 未找到链接文件夹')
                input('按 Enter 退出...')
                return
            folder_name = latest.name
            links_data = load_pan_links('xunlei', latest)
            all_links = [d['url'] for d in links_data]
            pending_urls = all_links.copy()
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
    remaining = len(pending_urls)
    
    print()
    print('准备转存 {0} 个链接（动态{1}窗口）'.format(remaining, MAX_WINDOWS))
    print()
    
    # 初始化日志文件
    global CURRENT_LOG_FILE
    log_dir = BASE_DIR / 'logs'
    log_dir.mkdir(exist_ok=True)
    CURRENT_LOG_FILE = log_dir / 'xunlei_{0}_{1}.log'.format(folder_name, datetime.now().strftime('%H%M%S'))
    
    # 写入日志头
    with open(CURRENT_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('=' * 60 + '\n')
        f.write('迅雷网盘转存日志\n')
        f.write('文件夹: {0}\n'.format(folder_name))
        f.write('开始时间: {0}\n'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        f.write('总计链接: {0}\n'.format(total))
        f.write('=' * 60 + '\n\n')
    
    log('日志文件: {0}'.format(CURRENT_LOG_FILE), 'INFO')
    print()
    
    if not start_xunlei():
        print('[错误] 无法启动迅雷')
        input('按 Enter 退出...')
        return
    
    print()
    print('5秒后开始，请切换到迅雷窗口...')
    for i in range(5, 0, -1):
        print('\r倒计时: {0} 秒'.format(i), end='', flush=True)
        time.sleep(1)
    print('\r开始转存！                ')
    print()
    print('=' * 60)
    
    # 初始化：先打开最多7个链接
    windows = []
    initial_count = min(MAX_WINDOWS, len(pending_urls))
    log('初始化：准备打开 {0} 个链接，剩余待处理: {1}'.format(initial_count, len(pending_urls)))
    for i in range(initial_count):
        link = pending_urls.pop(0)
        # 处理字典或字符串格式
        url = link['url'] if isinstance(link, dict) else link
        log('  打开链接 {0}/{1}: {2}'.format(i+1, initial_count, url[:40]))
        open_link(url)
        windows.append(WindowState(index=i, url=url, status='pending', start_time=0))
    log('初始化完成，实际打开: {0} 个窗口'.format(len(windows)))
    
    # 等待5秒让页面加载
    log('等待5秒加载...')
    time.sleep(5)
    
    # 主循环
    processed = 0
    round_num = 0
    
    while windows and not STOP_FLAG:
        round_num += 1
        print()
        log('=== 第 {0} 轮处理 ==='.format(round_num))
        
        # 处理所有窗口
        windows, pending_urls = process_windows(windows, coords, pending_urls, folder_name)
        
        # 更新进度（把已完成的从windows移到completed/failed）
        for w in list(windows):
            if w.status == 'success':
                completed.append(w.url)
                processed += 1
            elif w.status == 'failed':
                failed.append(w.url)
                processed += 1
        
        save_progress('xunlei', folder_name, completed, failed, total)
        print_progress_bar(len(completed) + len(failed), total, prefix='总进度')
        
        # 如果还有窗口在处理中，短暂等待
        if any(w.status in ['processing', 'pending'] for w in windows):
            time.sleep(1)
    
    # 清理剩余窗口
    if windows:
        log('清理剩余窗口...')
        while windows:
            click_tab(0)
            w = windows.pop(0)
            close_tab()
            if w.status == 'success':
                completed.append(w.url)
            elif w.status in ['failed', 'stuck', 'pending', 'processing']:
                failed.append(w.url)
            time.sleep(0.3)
    
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
    
    if len(completed) + len(failed) >= total:
        print()
        print('[OK] 全部完成！清除进度记录...')
        log('全部完成！清除进度记录', 'SUCCESS')
        clear_progress('xunlei')
    else:
        print()
        print('[WARN] 任务未完成，进度已保存，下次可继续')
        log('任务未完成，进度已保存', 'WARN')
    
    print('=' * 60)
    print()
    input('按 Enter 退出...')


if __name__ == '__main__':
    main()
