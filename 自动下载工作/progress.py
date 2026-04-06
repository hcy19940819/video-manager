# -*- coding: utf-8 -*-
"""
断点续传管理模块
"""

import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
PROGRESS_DIR = BASE_DIR / 'progress'
PROGRESS_DIR.mkdir(exist_ok=True)


def get_progress_file(pan_type):
    """获取进度文件路径"""
    return PROGRESS_DIR / f'{pan_type}_progress.json'


def load_progress(pan_type):
    """
    加载进度
    返回: {
        'folder': '时间戳文件夹名',
        'completed': ['url1', 'url2', ...],  # 已完成的链接
        'failed': ['url3', ...],  # 失败的链接
        'total': 100,
        'last_update': '2026-04-06 20:00:00'
    }
    """
    progress_file = get_progress_file(pan_type)
    if progress_file.exists():
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_progress(pan_type, folder, completed, failed, total):
    """保存进度"""
    progress_file = get_progress_file(pan_type)
    data = {
        'folder': str(folder) if folder else '',
        'completed': completed,
        'failed': failed,
        'total': total,
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clear_progress(pan_type):
    """清除进度"""
    progress_file = get_progress_file(pan_type)
    if progress_file.exists():
        progress_file.unlink()


def get_pending_links(pan_type, all_links, folder):
    """
    获取待处理的链接
    返回: (pending_links, is_resume, progress_info)
    """
    progress = load_progress(pan_type)
    
    # 检查是否有可继续的进度
    if progress and progress.get('folder') == str(folder):
        completed_set = set(progress.get('completed', []))
        failed_set = set(progress.get('failed', []))
        
        # 过滤出未处理的链接
        pending = []
        for link in all_links:
            url = link['url'] if isinstance(link, dict) else link
            if url not in completed_set:
                pending.append(link)
        
        if len(pending) < len(all_links):
            return pending, True, progress
    
    return all_links, False, None


def print_progress_bar(current, total, prefix='', length=30):
    """打印进度条"""
    filled = int(length * current // total)
    # 使用ASCII字符避免编码问题
    bar = '=' * filled + '-' * (length - filled)
    percent = 100 * current // total
    print('\r{0} [{1}] {2}/{3} ({4}%)'.format(prefix, bar, current, total, percent), end='', flush=True)
    if current >= total:
        print()  # 完成时换行
