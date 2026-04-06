# -*- coding: utf-8 -*-
import time
import json
from pathlib import Path
import pyautogui

print(u'='*60)
print(u'迅雷网盘 - 坐标校准')
print(u'='*60)
print()

coords_file = Path(u'xl_coords.json')
coords = {}

print(u'步骤1：将鼠标移到【转存到云盘】按钮')
input(u'到位后按 Enter 键...')

time.sleep(0.3)
x, y = pyautogui.position()

coords['save_btn'] = {'x': x, 'y': y}
print(u'转存按钮坐标：({0}, {1})'.format(x, y))

with open(coords_file, 'w', encoding='utf-8') as f:
    json.dump(coords, f, ensure_ascii=False, indent=2)

print()
print(u'='*60)
print(u'坐标已保存到：{0}'.format(coords_file))
print(u'='*60)

input(u'按 Enter 键退出...')
