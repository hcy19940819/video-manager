#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoFaceManager 管理面板启动入口
双击运行此文件启动Web界面
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 启动Web应用
from web.app import main

if __name__ == '__main__':
    main()
