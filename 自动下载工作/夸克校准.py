# -*- coding: utf-8 -*-
import time
import json
from pathlib import Path
import pyautogui

print('='*60)
print('夸克网盘 - 坐标校准')
print('='*60)
print()

coords_file = Path(__file__).parent / 'quark_coords.json'
coords = {}

print('步骤1：复制夸克分享链接，等待自动弹出下载窗口')
input('鼠标移到【保存到网盘】按钮，按 Enter...')

time.sleep(0.3)
x, y = pyautogui.position()

coords['save_btn'] = {'x': x, 'y': y}
print('保存按钮: ({0}, {1})'.format(x, y))

with open(coords_file, 'w', encoding='utf-8') as f:
    json.dump(coords, f, indent=2)

print()
print('='*60)
print('已保存: {0}'.format(coords_file))
print('='*60)
input('按 Enter 退出...')
