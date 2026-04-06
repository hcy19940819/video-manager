# -*- coding: utf-8 -*-
"""
窗口检测模块 - 通过控件文字识别网盘状态
"""

import win32gui
import win32con
import time


# 各网盘状态关键词映射
STATUS_KEYWORDS = {
    'baidu': {
        'wrong_code': ['提取码错误', '密码错误', '验证码错误'],
        'link_invalid': ['链接失效', '链接已过期', '分享已取消', '链接不存在'],
        'file_deleted': ['文件已被删除', '文件已删除', '资源已删除'],
        'need_login': ['请登录', '需要登录', '登录百度网盘'],
        'captcha': ['请输入验证码', '验证码'],
        'success': ['转存成功', '已保存到', '保存成功'],
        'limit': ['转存数量超限', '操作频繁', '请稍后再试'],
    },
    'uc': {
        'wrong_code': ['提取码错误', '密码错误'],
        'link_invalid': ['链接失效', '分享已取消', '链接不存在'],
        'file_deleted': ['文件已被删除', '资源已删除'],
        'need_login': ['请登录', '需要登录'],
        'success': ['保存成功', '已保存到网盘'],
        'limit': ['操作频繁', '请稍后再试'],
    },
    'xunlei': {
        'wrong_code': ['提取码错误', '密码错误'],
        'link_invalid': ['链接失效', '分享已取消', '链接不存在'],
        'file_deleted': ['文件已被删除', '资源已删除'],
        'need_login': ['请登录', '需要登录'],
        'success': ['转存成功', '已转存', '保存成功'],
        'limit': ['操作频繁', '请稍后再试'],
    },
    'quark': {
        'wrong_code': ['提取码错误', '密码错误'],
        'link_invalid': ['链接失效', '分享已取消'],
        'file_deleted': ['文件已被删除'],
        'need_login': ['请登录'],
        'success': ['保存成功', '已保存'],
        'limit': ['操作频繁'],
    }
}


def get_window_text(hwnd):
    """获取窗口文字"""
    try:
        return win32gui.GetWindowText(hwnd)
    except:
        return ''


def enum_child_windows(hwnd):
    """枚举所有子控件，返回文字列表"""
    texts = []
    
    def callback(child_hwnd, extra):
        text = get_window_text(child_hwnd)
        if text and len(text.strip()) > 0:
            texts.append(text.strip())
        return True
    
    try:
        win32gui.EnumChildWindows(hwnd, callback, None)
    except:
        pass
    
    return texts


def get_all_texts(hwnd=None, title_keywords=None):
    """
    获取窗口所有文字
    hwnd: 直接指定窗口句柄
    title_keywords: 通过标题关键词查找窗口
    """
    if hwnd is None and title_keywords:
        hwnd = find_window_by_title(title_keywords)
    
    if hwnd is None:
        return []
    
    # 获取主窗口文字 + 所有子控件文字
    all_texts = [get_window_text(hwnd)]
    all_texts.extend(enum_child_windows(hwnd))
    
    return [t for t in all_texts if t]


def find_window_by_title(keywords):
    """通过标题关键词查找窗口"""
    result = []
    
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = get_window_text(hwnd)
            for kw in keywords:
                if kw.lower() in title.lower():
                    result.append(hwnd)
                    return False
        return True
    
    try:
        win32gui.EnumWindows(callback, None)
    except:
        pass
    
    return result[0] if result else None


def detect_status(texts, pan_type):
    """
    检测状态
    返回: {'status': 'success'/'error'/'unknown', 'type': 'wrong_code'/..., 'message': '...'}
    
    注意：优先检查成功状态，避免页面同时显示错误和成功时误判
    """
    if not texts:
        return {'status': 'unknown', 'type': None, 'message': '无文字'}
    
    # 合并所有文字
    all_text = ' '.join(texts)
    
    keywords = STATUS_KEYWORDS.get(pan_type, {})
    
    # 优先检查成功状态
    success_words = keywords.get('success', [])
    for word in success_words:
        if word in all_text:
            return {'status': 'success', 'type': 'success', 'message': word}
    
    # 然后检查错误状态
    for status_type, words in keywords.items():
        if status_type == 'success':
            continue  # 已经检查过
        for word in words:
            if word in all_text:
                return {'status': 'error', 'type': status_type, 'message': word}
    
    return {'status': 'unknown', 'type': None, 'message': all_text[:100]}


def wait_for_status(pan_type, title_keywords, timeout=10, interval=0.5):
    """
    等待特定状态出现
    返回: {'found': True/False, 'status': {...}, 'timeout': True/False}
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        hwnd = find_window_by_title(title_keywords)
        if hwnd:
            texts = get_all_texts(hwnd)
            result = detect_status(texts, pan_type)
            
            if result['status'] != 'unknown':
                return {'found': True, 'status': result, 'timeout': False}
        
        time.sleep(interval)
    
    return {'found': False, 'status': None, 'timeout': True}


# 便捷函数
def detect_baidu_status(hwnd=None):
    """检测百度网盘状态"""
    texts = get_all_texts(hwnd, ['百度网盘', 'Baidu'])
    return detect_status(texts, 'baidu')


def detect_uc_status(hwnd=None):
    """检测UC网盘状态"""
    texts = get_all_texts(hwnd, ['UC', 'uc'])
    return detect_status(texts, 'uc')


def get_active_tab_text(hwnd):
    """只获取当前活动标签页的文字（可见且启用的控件）"""
    texts = []
    
    def callback(child_hwnd, extra):
        # 只读可见的控件
        if not win32gui.IsWindowVisible(child_hwnd):
            return True
        
        # 只读启用的控件（活动标签页的控件通常是启用的）
        if not win32gui.IsWindowEnabled(child_hwnd):
            return True
            
        text = win32gui.GetWindowText(child_hwnd)
        if text.strip():
            texts.append(text)
        return True
    
    try:
        win32gui.EnumChildWindows(hwnd, callback, None)
    except:
        pass
    
    return texts


def detect_xunlei_status(hwnd=None):
    """检测迅雷网盘状态 - 使用当前活动窗口的活动标签页"""
    if hwnd is None:
        # 获取当前前台窗口（活动窗口）
        hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        texts = get_active_tab_text(hwnd)
        return detect_status(texts, 'xunlei')
    return {'status': 'unknown', 'type': None, 'message': '无窗口'}


def detect_quark_status(hwnd=None):
    """检测夸克网盘状态"""
    texts = get_all_texts(hwnd, ['夸克', 'Quark'])
    return detect_status(texts, 'quark')
