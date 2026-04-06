# -*- coding: utf-8 -*-
import time
import json
from pathlib import Path
import pyautogui

print('='*60)
print('百度网盘 - 坐标校准')
print('='*60)
print()

coords_file = Path(__file__).parent / 'baidu_coords.json'
coords = {}

print('步骤1：复制百度分享链接，等待弹出转存窗口')
input('鼠标移到【转存】按钮，按 Enter...')

time.sleep(0.3)
x, y = pyautogui.position()

coords['save_btn'] = {'x': x, 'y': y}
print('转存按钮: ({0}, {1})'.format(x, y))

print()
print('='*60)
print('步骤2：点击转存后，鼠标移到【关闭页签】按钮')
input('到位后按 Enter...')

time.sleep(0.3)
x, y = pyautogui.position()

coords['close_btn'] = {'x': x, 'y': y}
print('关闭按钮: ({0}, {1})'.format(x, y))

with open(coords_file, 'w', encoding='utf-8') as f:
    json.dump(coords, f, indent=2)

print()
print('='*60)
print('已保存: {0}'.format(coords_file))
print('='*60)
input('按 Enter 退出...')
