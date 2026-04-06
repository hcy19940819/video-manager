# -*- coding: utf-8 -*-
"""
UC网盘自动转存工具
支持：断点续传、进度显示、关闭窗口即停止、日志记录
"""

import os
import sys
import time
import json
import signal
import re
from pathlib import Path
from datetime import datetime

import pyperclip
import pyautogui
import psutil

from progress import (
    load_progress, save_progress, clear_progress,
    get_pending_links, print_progress_bar
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

BASE_DIR = Path(__file__).parent
UC_PATH = r"D:/UC浏览器/uc.exe"
COORDS_FILE = BASE_DIR / 'auto_coords.json'
RUNTIME_LOG = []
STOP_FLAG = False
CURRENT_LOG_FILE = None


def signal_handler(sig, frame):
    global STOP_FLAG
    STOP_FLAG = True
    print('\n\n[用户中断] 正在保存进度并退出...')


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def log(msg, log_type='INFO'):
    """
    记录日志
    log_type: INFO/SUCCESS/ERROR/WARN
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


def is_uc_running():
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name'] or ''
            if 'uc' in name.lower():
                return True
        except:
            pass
    return False


def start_uc():
    if is_uc_running():
        log('UC浏览器已在运行', 'INFO')
        return True
    
    if os.path.exists(UC_PATH):
        log('启动UC浏览器...', 'INFO')
        os.startfile(UC_PATH)
        time.sleep(10)
        return True
    else:
        log('未找到UC: ' + UC_PATH, 'ERROR')
        return False


def parse_uc_links(folder):
    """解析UC链接"""
    links = []
    txt_file = folder / 'uc_pan_links.txt'
    
    if not txt_file.exists():
        return links
    
    with open(txt_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 按行号分割解析
    pattern = r'(\d+)\.\s+(https?://[^\s]+)(.*?)(?=\n\d+\.\s+https?://|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    for match in matches:
        url = match[1].strip()
        extra = match[2]
        
        # 清理URL
        url = url.strip()
        if '补：' in url:
            url = url.split('补：', 1)[0].strip()
        if '解压' in url:
            url = url.split('解压', 1)[0].strip()
        
        # 提取提取码
        code = ''
        code_match = re.search(r'提取码[:：]\s*(\w+)', extra)
        if code_match:
            code = code_match.group(1)
        
        if 'drive.uc.cn' in url:
            links.append({'url': url, 'code': code})
    
    return links


def process_link(link, coords):
    """处理单个链接"""
    url = link['url']
    code = link.get('code', '')
    
    try:
        # 1. 复制链接
        pyperclip.copy(url)
        time.sleep(0.5)
        
        # 2. 粘贴
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(3)
        
        # 3. 输入提取码（如果有）
        if code:
            pyperclip.copy(code)
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.5)
            pyautogui.press('enter')
            time.sleep(2)
        
        # 4. 点击【保存到网盘】（相对坐标）
        save_btn = coords.get('save_btn')
        if save_btn and 'rel_x' in save_btn:
            # 获取当前鼠标位置作为参考
            ref_x, ref_y = pyautogui.position()
            x = ref_x + save_btn['rel_x']
            y = ref_y + save_btn['rel_y']
            pyautogui.click(x, y)
        elif save_btn:
            pyautogui.click(save_btn['x'], save_btn['y'])
        else:
            return False
        
        time.sleep(2)
        
        # 5. 点击【知道了】关闭提示
        know_btn = coords.get('know_btn')
        if know_btn and 'rel_x' in know_btn:
            ref_x, ref_y = pyautogui.position()
            x = ref_x + know_btn['rel_x']
            y = ref_y + know_btn['rel_y']
            pyautogui.click(x, y)
            time.sleep(0.5)
        
        return True
        
    except Exception as e:
        log('失败: {0}'.format(e), 'ERROR')
        return False


def find_latest_folder(base_dir):
    if not base_dir.exists():
        return None
    folders = [f for f in base_dir.iterdir() if f.is_dir()]
    if not folders:
        return None
    return max(folders, key=lambda x: x.name)


def main():
    global STOP_FLAG, CURRENT_LOG_FILE
    
    print('=' * 60)
    print('UC网盘自动转存')
    print('=' * 60)
    print()
    print('提示：关闭此窗口即可停止程序')
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
    
    links_data = parse_uc_links(latest)
    all_links = links_data
    
    if not all_links:
        print('[错误] 没有待处理的链接')
        input('按 Enter 退出...')
        return
    
    # 检查断点续传
    pending_links, is_resume, progress = get_pending_links('uc', all_links, folder_name)
    
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
            clear_progress('uc')
            latest = find_latest_folder(stboy_dir)
            if not latest:
                print('[错误] 未找到链接文件夹')
                input('按 Enter 退出...')
                return
            folder_name = latest.name
            links_data = parse_uc_links(latest)
            all_links = links_data
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
    CURRENT_LOG_FILE = log_dir / 'uc_{0}_{1}.log'.format(folder_name, datetime.now().strftime('%H%M%S'))
    
    # 写入日志头
    with open(CURRENT_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('=' * 60 + '\n')
        f.write('UC网盘转存日志\n')
        f.write('文件夹: {0}\n'.format(folder_name))
        f.write('开始时间: {0}\n'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        f.write('总计链接: {0}\n'.format(total))
        f.write('=' * 60 + '\n\n')
    
    log('日志文件: {0}'.format(CURRENT_LOG_FILE), 'INFO')
    print()
    
    if not start_uc():
        print('[错误] 无法启动UC浏览器')
        input('按 Enter 退出...')
        return
    
    print()
    print('5秒后开始，请切换到UC浏览器窗口...')
    for i in range(5, 0, -1):
        print('\r倒计时: {0} 秒'.format(i), end='', flush=True)
        time.sleep(1)
    print('\r开始转存！                ')
    print()
    print('=' * 60)
    
    # 主循环
    processed = 0
    for i, link in enumerate(pending_links, 1):
        if STOP_FLAG:
            break
        
        current_num = len(completed) + len(failed) + 1
        url = link['url'] if isinstance(link, dict) else link
        
        print()
        print('[{0}/{1}] {2}'.format(current_num, total, url[:55]))
        log('处理 [{0}/{1}] {2}'.format(current_num, total, url[:50]), 'INFO')
        
        if process_link(link, coords):
            completed.append(url)
            log('转存成功', 'SUCCESS')
        else:
            failed.append(url)
            log('转存失败', 'ERROR')
        
        processed += 1
        
        # 保存进度
        save_progress('uc', folder_name, completed, failed, total)
        
        # 显示总进度
        print_progress_bar(len(completed) + len(failed), total, prefix='总进度')
        
        if i < len(pending_links) and not STOP_FLAG:
            time.sleep(1)
    
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
    
    if len(completed) + len(failed) >= total:
        print()
        print('[OK] 全部完成！清除进度记录...')
        log('全部完成！清除进度记录', 'SUCCESS')
        clear_progress('uc')
    else:
        print()
        print('[WARN] 任务未完成，进度已保存，下次可继续')
        log('任务未完成，进度已保存', 'WARN')
    
    print('=' * 60)
    print()
    input('按 Enter 退出...')


if __name__ == '__main__':
    main()
