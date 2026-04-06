# -*- coding: utf-8 -*-
"""
夸克网盘自动转存工具
支持：断点续传、进度显示、关闭窗口即停止、日志记录
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

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

BASE_DIR = Path(__file__).parent
QUARK_LNK = r'C:/Users/HCY/Desktop/夸克.lnk'
COORDS_FILE = BASE_DIR / 'quark_coords.json'
RUNTIME_LOG = []
STOP_FLAG = False
CURRENT_LOG_FILE = None


def signal_handler(sig, frame):
    """处理Ctrl+C或窗口关闭"""
    global STOP_FLAG
    STOP_FLAG = True
    print('\n\n[用户中断] 正在保存进度并退出...')


# 注册信号处理
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


def is_quark_running():
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name'] or ''
            if 'quark' in name.lower() or '夸克' in name:
                return True
        except:
            pass
    return False


def start_quark():
    if is_quark_running():
        log('夸克网盘已在运行，跳过启动', 'INFO')
        return True
    
    if os.path.exists(QUARK_LNK):
        log('启动夸克网盘...', 'INFO')
        os.startfile(QUARK_LNK)
        time.sleep(10)
        log('启动成功', 'SUCCESS')
        return True
    else:
        log('未找到快捷方式: ' + QUARK_LNK, 'ERROR')
        return False


def process_link(url, coords):
    """处理单个链接，返回是否成功"""
    try:
        # 1. 复制链接
        pyperclip.copy(url)
        time.sleep(0.5)
        
        # 2. 粘贴链接（夸克自动检测）
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(3)  # 等待自动弹出窗口
        
        # 3. 点击【保存到网盘】
        save_btn = coords.get('save_btn')
        if save_btn:
            pyautogui.click(save_btn['x'], save_btn['y'])
        else:
            return False
        
        # 4. 等待2秒
        time.sleep(2)
        return True
        
    except Exception as e:
        log('失败: {0}'.format(e), 'ERROR')
        return False


def find_latest_folder(base_dir):
    """查找最新的时间戳文件夹"""
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
            if pan_type == 'quark' and 'pan.quark.cn' in line:
                links.append({'url': line, 'code': ''})
    return links


def main():
    global STOP_FLAG, CURRENT_LOG_FILE
    
    print('=' * 60)
    print('夸克网盘自动转存')
    print('=' * 60)
    print()
    print('提示：关闭此窗口即可停止程序')
    print()
    
    coords = load_coords()
    if not coords:
        print('[错误] 未找到坐标，请先校准坐标')
        input('按 Enter 退出...')
        return
    
    log('坐标已加载', 'INFO')
    
    # 加载链接
    stboy_dir = Path(r'D:/AI/AI_Tool/STboy_Auto/extracted_links')
    latest = find_latest_folder(stboy_dir)
    
    if not latest:
        print('[错误] 未找到链接文件夹')
        input('按 Enter 退出...')
        return
    
    folder_name = latest.name
    
    links_data = load_pan_links('quark', latest)
    all_links = [d['url'] for d in links_data]
    
    if not all_links:
        print('[错误] 没有待处理的链接')
        input('按 Enter 退出...')
        return
    
    # 检查断点续传
    pending_links, is_resume, progress = get_pending_links('quark', all_links, folder_name)
    
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
            clear_progress('quark')
            latest = find_latest_folder(stboy_dir)
            if not latest:
                print('[错误] 未找到链接文件夹')
                input('按 Enter 退出...')
                return
            folder_name = latest.name
            links_data = load_pan_links('quark', latest)
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
    CURRENT_LOG_FILE = log_dir / 'quark_{0}_{1}.log'.format(folder_name, datetime.now().strftime('%H%M%S'))
    
    # 写入日志头
    with open(CURRENT_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('=' * 60 + '\n')
        f.write('夸克网盘转存日志\n')
        f.write('文件夹: {0}\n'.format(folder_name))
        f.write('开始时间: {0}\n'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        f.write('总计链接: {0}\n'.format(total))
        f.write('=' * 60 + '\n\n')
    
    log('日志文件: {0}'.format(CURRENT_LOG_FILE), 'INFO')
    print()
    
    if not start_quark():
        print('[错误] 无法启动夸克网盘')
        input('按 Enter 退出...')
        return
    
    print()
    print('5秒后开始，请切换到夸克网盘窗口...')
    for i in range(5, 0, -1):
        print('\r倒计时: {0} 秒'.format(i), end='', flush=True)
        time.sleep(1)
    print('\r开始转存！                ')
    print()
    print('=' * 60)
    
    # 主循环
    processed = 0
    for i, url in enumerate(pending_links, 1):
        if STOP_FLAG:
            break
        
        current_num = len(completed) + len(failed) + 1
        
        print()
        print('[{0}/{1}] {2}'.format(current_num, total, url[:55]))
        log('处理 [{0}/{1}] {2}'.format(current_num, total, url[:50]), 'INFO')
        
        if process_link(url, coords):
            completed.append(url)
            log('转存成功', 'SUCCESS')
        else:
            failed.append(url)
            log('转存失败', 'ERROR')
        
        processed += 1
        
        # 保存进度
        save_progress('quark', folder_name, completed, failed, total)
        
        # 显示总进度
        print_progress_bar(len(completed) + len(failed), total, prefix='总进度')
        
        if i < len(pending_links) and not STOP_FLAG:
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
    
    if len(completed) + len(failed) >= total:
        print()
        print('[OK] 全部完成！清除进度记录...')
        log('全部完成！清除进度记录', 'SUCCESS')
        clear_progress('quark')
    else:
        print()
        print('[WARN] 任务未完成，进度已保存，下次可继续')
        log('任务未完成，进度已保存', 'WARN')
    
    print('=' * 60)
    print()
    input('按 Enter 退出...')


if __name__ == '__main__':
    main()
