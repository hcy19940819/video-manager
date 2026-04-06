# -*- coding: utf-8 -*-
"""
多网盘自动转存工具 - 统一入口
支持：UC网盘、百度网盘、迅雷网盘、夸克网盘
功能：断点续传、进度显示、关闭窗口即停止
"""

import os
import sys
import subprocess
from pathlib import Path

# 设置编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent

PAN_LIST = {
    '1': {'name': 'UC网盘', 'script': 'uc_auto_v2.py', 'coords': 'auto_coords.json', 'key': 'uc'},
    '2': {'name': '百度网盘', 'script': '百度网盘转存.py', 'coords': 'baidu_coords.json', 'key': 'baidu'},
    '3': {'name': '迅雷网盘', 'script': 'xl.py', 'coords': 'xl_coords.json', 'key': 'xunlei'},
    '4': {'name': '夸克网盘', 'script': '夸克网盘转存.py', 'coords': 'quark_coords.json', 'key': 'quark'},
}


def check_progress(pan_key):
    """检查是否有未完成的进度"""
    progress_file = BASE_DIR / 'progress' / f'{pan_key}_progress.json'
    if progress_file.exists():
        try:
            import json
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            completed = len(data.get('completed', []))
            failed = len(data.get('failed', []))
            total = data.get('total', 0)
            if total > 0 and (completed + failed) < total:
                return f'断点续传 ({completed+failed}/{total})'
        except:
            pass
    return None


def show_menu():
    """显示主菜单"""
    print()
    print('=' * 60)
    print('多网盘自动转存工具')
    print('=' * 60)
    print()
    print('请选择网盘：')
    for key, info in PAN_LIST.items():
        # 检查坐标是否存在
        coords_file = BASE_DIR / info['coords']
        if coords_file.exists():
            # 检查是否有断点续传
            progress_status = check_progress(info['key'])
            if progress_status:
                status = progress_status
            else:
                status = '已校准'
        else:
            status = '未校准'
        print('  {0}. {1} ({2})'.format(key, info['name'], status))
    print()
    print('  10. 校准坐标')
    print('  0. 退出')
    print()
    print('=' * 60)


def show_calibrate_menu():
    """显示校准菜单"""
    print()
    print('=' * 60)
    print('坐标校准')
    print('=' * 60)
    print()
    print('请选择网盘：')
    for key, info in PAN_LIST.items():
        print('  {0}. {1}'.format(key, info['name']))
    print()
    print('  10. 通用坐标读取')
    print('  0. 返回主菜单')
    print()
    print('=' * 60)


def run_transfer(pan_id):
    """运行转存"""
    info = PAN_LIST.get(pan_id)
    if not info:
        print('[错误] 无效选择')
        return
    
    script_file = BASE_DIR / info['script']
    if not script_file.exists():
        print('[错误] 未找到脚本: {0}'.format(info['script']))
        return
    
    print()
    print('启动 {0}...'.format(info['name']))
    print('提示：关闭弹出的黑窗即可停止程序')
    print()
    
    # 使用 CREATE_NEW_CONSOLE 创建新控制台窗口
    subprocess.run(['python', str(script_file)], cwd=str(BASE_DIR), creationflags=subprocess.CREATE_NEW_CONSOLE)


def run_calibrate(pan_id):
    """运行校准"""
    info = PAN_LIST.get(pan_id)
    if not info:
        print('[错误] 无效选择')
        return
    
    calibrate_scripts = {
        '1': '获取UC坐标.py',
        '2': '百度校准.py',
        '3': '迅雷校准.py',
        '4': '夸克校准.py',
    }
    
    script_name = calibrate_scripts.get(pan_id)
    if script_name:
        script_file = BASE_DIR / script_name
        if script_file.exists():
            subprocess.run(['python', str(script_file)], cwd=str(BASE_DIR))
        else:
            print('[错误] 未找到校准脚本')


def run_general_coord():
    """运行通用坐标读取"""
    script_file = BASE_DIR / '读取坐标.py'
    if script_file.exists():
        subprocess.run(['python', str(script_file)], cwd=str(BASE_DIR))
    else:
        print('[错误] 未找到读取坐标脚本')


def main():
    """主函数"""
    while True:
        show_menu()
        choice = input('请输入选项: ').strip()
        
        if choice == '0':
            print('退出')
            break
        
        elif choice == '10':
            # 校准菜单
            while True:
                show_calibrate_menu()
                cal_choice = input('请输入选项: ').strip()
                
                if cal_choice == '0':
                    break
                elif cal_choice == '10':
                    run_general_coord()
                elif cal_choice in PAN_LIST:
                    run_calibrate(cal_choice)
                else:
                    print('[错误] 无效选择')
        
        elif choice in PAN_LIST:
            run_transfer(choice)
        
        else:
            print('[错误] 无效选择')


if __name__ == '__main__':
    main()
