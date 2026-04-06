# -*- coding: utf-8 -*-
"""
通用坐标读取工具
使用方法：
1. 运行脚本
2. 将鼠标移到目标位置
3. 按 Enter 键记录坐标
4. 可连续记录多个坐标
5. 输入 q 退出
"""

import time
import pyautogui

print('=' * 60)
print('通用坐标读取工具')
print('=' * 60)
print()
print('操作说明：')
print('  1. 将鼠标移到目标位置')
print('  2. 按 Enter 记录坐标')
print('  3. 输入 q 退出')
print()
print('=' * 60)
print()

coords_list = []

while True:
    user_input = input('准备记录坐标，按 Enter 读取（或输入 q 退出）: ').strip().lower()
    
    if user_input == 'q':
        break
    
    # 等待一小段时间让用户稳定鼠标
    time.sleep(0.5)
    
    # 获取当前鼠标位置
    x, y = pyautogui.position()
    
    # 记录坐标
    coord = {'x': x, 'y': y}
    coords_list.append(coord)
    
    print()
    print('  坐标 {0}: ({1}, {2})'.format(len(coords_list), x, y))
    print()

# 输出所有坐标
if coords_list:
    print()
    print('=' * 60)
    print('记录的坐标：')
    print('=' * 60)
    for i, coord in enumerate(coords_list, 1):
        print('  坐标 {0}: ({1}, {2})'.format(i, coord['x'], coord['y']))
    
    # 输出JSON格式
    print()
    print('JSON格式：')
    import json
    print(json.dumps(coords_list, indent=2))
    print('=' * 60)

print()
input('按 Enter 退出...')
