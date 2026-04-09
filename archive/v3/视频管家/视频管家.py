#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 视频管家 - 高度整合版
功能：视频去重 + AI人物识别 + 库管理可视化
版本：v2.0 整合版
特点：单文件核心，简洁高效
"""

import os
import sys
import json
import sqlite3
import hashlib
import argparse
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import concurrent.futures

# ============ 可选依赖 ============
try:
    from tqdm import tqdm
    有进度条 = True
except ImportError:
    有进度条 = False
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.it = iterable
            if desc: print(f"{desc}...")
        def __iter__(self): 
            for x in self.it or []: yield x
        def update(self, n=1): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

try:
    import cv2
    import numpy as np
    有视频处理 = True
except ImportError:
    有视频处理 = False

try:
    import insightface
    有人脸识别 = True
except ImportError:
    有人脸识别 = False

# ============ 全局配置 ============
视频后缀 = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'}
项目目录 = Path(__file__).parent
数据目录 = 项目目录 / "data"

# ============ 数据模型 ============
@dataclass
class 视频指纹:
    路径: str
    大小: int
    修改时间: float
    时长: float = 0.0
    宽度: int = 0
    高度: int = 0
    帧率: float = 0.0
    快速哈希: str = ""
    文件哈希: str = ""
    创建时间: str = ""
    def __post_init__(self):
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()

@dataclass
class 人物记录:
    路径: str
    人物名: str
    时间点: List[float]
    置信度: float
    截图路径: List[str]
    创建时间: str = ""
    def __post_init__(self):
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()

@dataclass
class 视频库:
    路径: str
    名称: str = ""
    状态: str = "未分类"  # 未分类/分类中/已分类
    人物: List[str] = None
    视频数: int = 0
    总大小: int = 0
    总时长: float = 0.0
    扫描时间: str = ""
    创建时间: str = ""
    def __post_init__(self):
        if not self.名称: self.名称 = Path(self.路径).name
        if self.人物 is None: self.人物 = []
        if not self.创建时间: self.创建时间 = datetime.now().isoformat()

# ============ 数据库管理（统一） ============
class 数据库:
    """统一数据库管理"""
    
    def __init__(self):
        数据目录.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(数据目录 / "video_manager.db")
        self.conn.row_factory = sqlite3.Row
        self.初始化()
    
    def 初始化(self):
        """初始化所有表"""
        cursor = self.conn.cursor()
        
        # 视频指纹表（去重）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                size INTEGER,
                mtime REAL,
                duration REAL DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                fps REAL DEFAULT 0,
                ahash TEXT,
                md5 TEXT,
                created TEXT
            )
        ''')
        
        # 人物记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                name TEXT NOT NULL,
                timestamps TEXT,  -- JSON数组
                confidence REAL,
                screenshots TEXT, -- JSON数组
                created TEXT
            )
        ''')
        
        # 视频库表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS libraries (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                name TEXT,
                status TEXT DEFAULT '未分类',
                persons TEXT,  -- JSON数组
                video_count INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                total_duration REAL DEFAULT 0,
                scanned TEXT,
                created TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_videos_ahash ON videos(ahash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_libs_status ON libraries(status)')
        self.conn.commit()
    
    # ============ 视频操作 ============
    def 保存视频(self, v: 视频指纹):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO videos 
            (path, size, mtime, duration, width, height, fps, ahash, md5, created)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (v.路径, v.大小, v.修改时间, v.时长, v.宽度, v.高度, v.帧率, 
              v.快速哈希, v.文件哈希, v.创建时间))
        self.conn.commit()
    
    def 获取所有视频(self) -> List[视频指纹]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM videos')
        return [视频指纹(
            路径=r['path'], 大小=r['size'], 修改时间=r['mtime'],
            时长=r['duration'], 宽度=r['width'], 高度=r['height'], 帧率=r['fps'],
            快速哈希=r['ahash'] or '', 文件哈希=r['md5'] or '', 创建时间=r['created'] or ''
        ) for r in cursor.fetchall()]
    
    def 获取已有路径(self) -> set:
        cursor = self.conn.cursor()
        cursor.execute('SELECT path FROM videos')
        return {r[0] for r in cursor.fetchall()}
    
    # ============ 人物操作 ============
    def 保存人物(self, p: 人物记录):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO persons 
            (path, name, timestamps, confidence, screenshots, created)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (p.路径, p.人物名, json.dumps(p.时间点), p.置信度, 
              json.dumps(p.截图路径), p.创建时间))
        self.conn.commit()
    
    def 获取所有人物(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT DISTINCT name FROM persons ORDER BY name')
        return [{'name': r[0]} for r in cursor.fetchall()]
    
    def 搜索人物(self, name: str) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT path, timestamps, confidence FROM persons WHERE name = ?', (name,))
        return [{'path': r[0], 'timestamps': json.loads(r[1]), 'confidence': r[2]} 
                for r in cursor.fetchall()]
    
    # ============ 库操作 ============
    def 保存库(self, lib: 视频库):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO libraries 
            (path, name, status, persons, video_count, total_size, total_duration, scanned, created)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (lib.路径, lib.名称, lib.状态, json.dumps(lib.人物),
              lib.视频数, lib.总大小, lib.总时长, lib.扫描时间, lib.创建时间))
        self.conn.commit()
    
    def 获取所有库(self) -> List[视频库]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM libraries ORDER BY created DESC')
        rows = cursor.fetchall()
        return [视频库(
            路径=r['path'], 名称=r['name'], 状态=r['status'],
            人物=json.loads(r['persons']) if r['persons'] else [],
            视频数=r['video_count'], 总大小=r['total_size'],
            总时长=r['total_duration'], 扫描时间=r['scanned'] or '',
            创建时间=r['created'] or ''
        ) for r in rows]
    
    def 删除库(self, path: str):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM libraries WHERE path = ?', (path,))
        self.conn.commit()
    
    def 关闭(self):
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.关闭()

# ============ 核心功能类 ============
class 视频处理器:
    """视频处理核心"""
    
    def __init__(self, 模式: str = "快速"):
        self.模式 = 模式
        self.人脸检测 = None
        self.已处理大小 = 0
        self.休息次数 = 0
        
        if 有人脸识别 and 模式 != "简单":
            try:
                self.人脸检测 = insightface.app.FaceAnalysis()
                self.人脸检测.prepare(ctx_id=-1, det_size=(640, 640))
                print("✓ AI模型加载成功")
            except Exception as e:
                print(f"✗ AI模型加载失败: {e}")
    
    def 扫描(self, paths: List[str], 增量: bool = True, 
             硬盘保护: int = 100, 休息秒: int = 10) -> Dict:
        """扫描视频"""
        print(f"\n{'='*60}")
        print(f"🎬 开始扫描 [模式: {self.模式}]")
        print(f"   硬盘保护: 每{硬盘保护}GB休息{休息秒}秒" if 硬盘保护 > 0 else "   硬盘保护: 关闭")
        print(f"{'='*60}")
        
        # 收集视频
        videos = []
        for p in paths:
            videos.extend(self.收集视频(p))
        
        if not videos:
            print("未找到视频")
            return {'videos': 0, 'persons': 0}
        
        print(f"发现 {len(videos)} 个视频")
        
        # 增量过滤
        if 增量:
            with 数据库() as db:
                已有 = db.获取已有路径()
            videos = [v for v in videos if v not in 已有]
            print(f"新增视频: {len(videos)} 个")
        
        if not videos:
            return {'videos': 0, 'persons': 0}
        
        # 处理
        批量大小 = 硬盘保护 * 1024 * 1024 * 1024 if 硬盘保护 > 0 else float('inf')
        视频计数 = 0
        人物计数 = 0
        
        iterator = tqdm(videos, desc="处理视频") if 有进度条 else videos
        
        with 数据库() as db:
            for path in iterator:
                try:
                    结果 = self.处理单个视频(path, db)
                    视频计数 += 1
                    人物计数 += 结果.get('persons', 0)
                    
                    # 硬盘保护
                    file_size = Path(path).stat().st_size
                    self.已处理大小 += file_size
                    
                    if 硬盘保护 > 0 and self.已处理大小 >= 批量大小:
                        self._休息(休息秒)
                        self.已处理大小 = 0
                        self.休息次数 += 1
                        
                except Exception as e:
                    print(f"✗ {Path(path).name}: {e}")
        
        print(f"\n✅ 扫描完成: {视频计数} 个视频, {人物计数} 个人物记录")
        return {'videos': 视频计数, 'persons': 人物计数, 'rests': self.休息次数}
    
    def 收集视频(self, path: str) -> List[str]:
        """收集目录下所有视频"""
        p = Path(path)
        if p.is_file() and p.suffix.lower() in 视频后缀:
            return [str(p.absolute())]
        
        results = []
        for ext in 视频后缀:
            results.extend(str(f.absolute()) for f in p.rglob(f"*{ext}"))
        return results
    
    def 处理单个视频(self, path: str, db: 数据库) -> Dict:
        """处理单个视频"""
        stat = Path(path).stat()
        
        # 基础信息
        v = 视频指纹(路径=path, 大小=stat.st_size, 修改时间=stat.st_mtime)
        
        # 视频信息
        if 有视频处理:
            cap = cv2.VideoCapture(path)
            if cap.isOpened():
                v.帧率 = cap.get(cv2.CAP_PROP_FPS)
                v.宽度 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                v.高度 = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                v.时长 = cap.get(cv2.CAP_PROP_FRAME_COUNT) / v.帧率 if v.帧率 > 0 else 0
            
            # 计算哈希
            v.快速哈希 = self._计算ahash(cap)
            v.文件哈希 = self._计算md5(path)
            
            # 人物识别
            persons = []
            if self.人脸检测 and self.模式 != "简单":
                persons = self._识别人物(cap, path)
                for p in persons:
                    db.保存人物(p)
            
            cap.release()
        
        db.保存视频(v)
        return {'persons': len(persons)}
    
    def _计算ahash(self, cap) -> str:
        """计算平均哈希"""
        if not cap or not cap.isOpened():
            return ""
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(cv2.CAP_PROP_FRAME_COUNT) / 2)
        ret, frame = cap.read()
        if not ret:
            return ""
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (8, 8))
        mean = small.mean()
        bits = (small > mean).flatten()
        return ''.join(['1' if b else '0' for b in bits])
    
    def _计算md5(self, path: str) -> str:
        """计算文件前1MB的MD5"""
        try:
            h = hashlib.md5()
            with open(path, 'rb') as f:
                h.update(f.read(1024 * 1024))
            return h.hexdigest()[:16]
        except:
            return ""
    
    def _识别人物(self, cap, path: str) -> List[人物记录]:
        """识别人物"""
        if not cap or not cap.isOpened():
            return []
        
        # 采样配置
        if self.模式 == "深度":
            间隔 = 3
            最大帧 = 50
        else:  # 快速
            间隔 = 10
            最大帧 = 10
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        帧间隔 = int(fps * 间隔)
        总帧数 = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        人脸数据 = defaultdict(lambda: {'times': [], 'conf': [], 'faces': []})
        
        for i in range(0, min(总帧数, 帧间隔 * 最大帧), 帧间隔):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret:
                break
            
            faces = self.人脸检测.get(frame)
            for face in faces:
                if face.det_score < 0.7:
                    continue
                
                # 简单匹配（用特征向量的简单方式）
                face_id = f"face_{id(face.embedding.tobytes()) % 10000}"
                人脸数据[face_id]['times'].append(i / fps)
                人脸数据[face_id]['conf'].append(float(face.det_score))
        
        # 生成记录
        records = []
        for face_id, data in 人脸数据.items():
            if len(data['times']) >= 2:  # 至少出现2次
                records.append(人物记录(
                    路径=path,
                    人物名=f"未知人物_{face_id}",
                    时间点=sorted(data['times']),
                    置信度=sum(data['conf']) / len(data['conf']),
                    截图路径=[]
                ))
        
        return records
    
    def _休息(self, seconds: int):
        """硬盘保护休息"""
        print(f"\n💤 硬盘保护: 休息 {seconds} 秒...")
        for i in range(seconds, 0, -1):
            print(f"   剩余 {i} 秒...", end='\r')
            time.sleep(1)
        print("   继续扫描!         ")
    
    def 查找重复(self, 阈值: int = 10) -> List[Dict]:
        """查找重复视频"""
        print("\n🔍 查找重复视频...")
        
        with 数据库() as db:
            videos = db.获取所有视频()
        
        if not videos:
            print("视频库为空")
            return []
        
        # 按大小分组
        by_size = defaultdict(list)
        for v in videos:
            by_size[v.大小].append(v)
        
        # 检查重复
        重复组 = []
        已处理 = set()
        
        for videos in by_size.values():
            if len(videos) < 2:
                continue
            
            for i, v1 in enumerate(videos):
                if v1.路径 in 已处理:
                    continue
                
                组 = [v1]
                for v2 in videos[i+1:]:
                    if v2.路径 in 已处理:
                        continue
                    
                    # 快速哈希比较
                    if v1.快速哈希 and v2.快速哈希:
                        diff = sum(c1 != c2 for c1, c2 in zip(v1.快速哈希, v2.快速哈希))
                        if diff <= 阈值:
                            组.append(v2)
                            已处理.add(v2.路径)
                
                if len(组) > 1:
                    已处理.add(v1.路径)
                    重复组.append({
                        'files': [v.路径 for v in 组],
                        'count': len(组),
                        'size': v1.大小
                    })
        
        print(f"发现 {len(重复组)} 组重复视频")
        return 重复组

# ============ 库管理功能 ============
class 库管理器:
    """视频库管理"""
    
    def 添加库(self, path: str) -> bool:
        """添加视频库"""
        p = Path(path)
        if not p.exists():
            print(f"✗ 路径不存在: {path}")
            return False
        
        # 统计
        videos = list(p.rglob("*"))
        videos = [v for v in videos if v.suffix.lower() in 视频后缀]
        
        total_size = sum(v.stat().st_size for v in videos)
        
        lib = 视频库(
            路径=str(p.absolute()),
            视频数=len(videos),
            总大小=total_size
        )
        
        with 数据库() as db:
            db.保存库(lib)
        
        print(f"✅ 添加库: {lib.名称}")
        print(f"   视频: {lib.视频数} 个")
        print(f"   大小: {total_size / (1024**3):.2f} GB")
        return True
    
    def 列出库(self):
        """列出所有库"""
        with 数据库() as db:
            libs = db.获取所有库()
        
        if not libs:
            print("暂无视频库")
            return
        
        print(f"\n📚 视频库列表 ({len(libs)} 个)")
        print("-" * 80)
        for lib in libs:
            status_icon = {"未分类": "📦", "分类中": "⏳", "已分类": "✅"}.get(lib.状态, "📦")
            print(f"{status_icon} {lib.名称}")
            print(f"   路径: {lib.路径}")
            print(f"   状态: {lib.状态} | 视频: {lib.视频数} 个 | 大小: {lib.总大小 / (1024**3):.2f} GB")
            if lib.人物:
                print(f"   人物: {', '.join(lib.人物)}")
            print()
    
    def 更新状态(self, path: str, status: str):
        """更新库状态"""
        with 数据库() as db:
            libs = db.获取所有库()
            for lib in libs:
                if lib.路径 == path:
                    lib.状态 = status
                    lib.扫描时间 = datetime.now().isoformat()
                    db.保存库(lib)
                    print(f"✅ 更新状态: {lib.名称} -> {status}")
                    return True
        print(f"✗ 未找到库: {path}")
        return False
    
    def 删除库(self, path: str):
        """删除库"""
        with 数据库() as db:
            db.删除库(path)
        print(f"✅ 已删除库: {path}")

# ============ Web界面 ============
def 启动Web界面(端口: int = 5000):
    """启动Web管理界面"""
    try:
        from flask import Flask, jsonify, request, render_template_string
    except ImportError:
        print("✗ 请先安装 Flask: pip install flask")
        return
    
    app = Flask(__name__)
    
    HTML = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>视频管家 - Web控制台</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: #333;
            }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .header {
                background: rgba(255,255,255,0.95);
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            }
            .header h1 { color: #667eea; font-size: 2.5em; margin-bottom: 10px; }
            .header p { color: #666; font-size: 1.1em; }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            .stat-card {
                background: rgba(255,255,255,0.95);
                border-radius: 10px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }
            .stat-card h3 { color: #667eea; font-size: 2em; margin-bottom: 5px; }
            .stat-card p { color: #666; }
            .section {
                background: rgba(255,255,255,0.95);
                border-radius: 15px;
                padding: 25px;
                margin-bottom: 20px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }
            .section h2 { color: #667eea; margin-bottom: 20px; border-bottom: 2px solid #eee; padding-bottom: 10px; }
            .lib-card {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 15px;
                border-left: 4px solid #667eea;
            }
            .lib-card h3 { color: #333; margin-bottom: 10px; }
            .lib-card p { color: #666; margin: 5px 0; }
            .lib-card .status { 
                display: inline-block; 
                padding: 4px 12px; 
                border-radius: 20px; 
                font-size: 0.85em; 
                margin-top: 10px;
            }
            .status-未分类 { background: #ffebee; color: #c62828; }
            .status-分类中 { background: #fff3e0; color: #ef6c00; }
            .status-已分类 { background: #e8f5e9; color: #2e7d32; }
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 25px;
                cursor: pointer;
                font-size: 1em;
                margin: 5px;
                transition: transform 0.2s;
            }
            .btn:hover { transform: translateY(-2px); }
            .input-group { margin: 15px 0; }
            .input-group input {
                padding: 12px 15px;
                border: 2px solid #ddd;
                border-radius: 8px;
                width: 300px;
                font-size: 1em;
            }
            .input-group input:focus {
                outline: none;
                border-color: #667eea;
            }
            .empty { text-align: center; color: #999; padding: 40px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎬 视频管家</h1>
                <p>本地视频管理系统 - 去重 + 人物识别 + 库管理</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <h3 id="lib-count">0</h3>
                    <p>视频库</p>
                </div>
                <div class="stat-card">
                    <h3 id="video-count">0</h3>
                    <p>视频文件</p>
                </div>
                <div class="stat-card">
                    <h3 id="person-count">0</h3>
                    <p>识别人物</p>
                </div>
            </div>
            
            <div class="section">
                <h2>➕ 添加视频库</h2>
                <div class="input-group">
                    <input type="text" id="lib-path" placeholder="输入视频文件夹路径">
                    <button class="btn" onclick="addLib()">添加</button>
                </div>
            </div>
            
            <div class="section">
                <h2>📚 视频库列表</h2>
                <div id="lib-list">
                    <div class="empty">暂无视频库</div>
                </div>
            </div>
        </div>
        
        <script>
            async function loadStats() {
                try {
                    const res = await fetch("/api/stats");
                    const data = await res.json();
                    document.getElementById("lib-count").textContent = data.libraries || 0;
                    document.getElementById("video-count").textContent = data.videos || 0;
                    document.getElementById("person-count").textContent = data.persons || 0;
                } catch(e) { console.error(e); }
            }
            
            async function loadLibs() {
                try {
                    const res = await fetch("/api/libraries");
                    const data = await res.json();
                    const container = document.getElementById("lib-list");
                    
                    if (data.length === 0) {
                        container.innerHTML = '<div class="empty">暂无视频库</div>';
                        return;
                    }
                    
                    container.innerHTML = data.map(lib => `
                        <div class="lib-card">
                            <h3>${lib.name}</h3>
                            <p>📁 ${lib.path}</p>
                            <p>🎬 ${lib.video_count} 个视频 | 💾 ${(lib.total_size / 1024**3).toFixed(2)} GB</p>
                            ${lib.persons.length ? `<p>👤 ${lib.persons.join(", ")}</p>` : ""}
                            <span class="status status-${lib.status}">${lib.status}</span>
                        </div>
                    `).join("");
                } catch(e) { console.error(e); }
            }
            
            async function addLib() {
                const path = document.getElementById("lib-path").value.trim();
                if (!path) return alert("请输入路径");
                
                try {
                    const res = await fetch("/api/libraries", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({path: path})
                    });
                    const data = await res.json();
                    if (data.success) {
                        document.getElementById("lib-path").value = "";
                        loadStats();
                        loadLibs();
                        alert("添加成功");
                    } else {
                        alert("添加失败: " + data.error);
                    }
                } catch(e) { alert("错误: " + e); }
            }
            
            loadStats();
            loadLibs();
        </script>
    </body>
    </html>
    '''
    
    @app.route('/')
    def index():
        return render_template_string(HTML)
    
    @app.route('/api/stats')
    def stats():
        with 数据库() as db:
            libs = db.获取所有库()
            videos = db.获取所有视频()
            persons = db.获取所有人物()
        return jsonify({
            'libraries': len(libs),
            'videos': len(videos),
            'persons': len(persons)
        })
    
    @app.route('/api/libraries')
    def libraries():
        with 数据库() as db:
            libs = db.获取所有库()
        return jsonify([{
            'path': l.路径,
            'name': l.名称,
            'status': l.状态,
            'video_count': l.视频数,
            'total_size': l.总大小,
            'persons': l.人物
        } for l in libs])
    
    @app.route('/api/libraries', methods=['POST'])
    def add_library():
        data = request.get_json()
        path = data.get('path', '')
        
        mgr = 库管理器()
        if mgr.添加库(path):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '添加失败'})
    
    print(f"\n🌐 Web界面启动成功!")
    print(f"   本地访问: http://localhost:{端口}")
    print(f"   按 Ctrl+C 停止\n")
    
    app.run(host='0.0.0.0', port=端口, debug=False)

# ============ 命令行入口 ============
def main():
    parser = argparse.ArgumentParser(description='视频管家 - 视频去重+人物识别+库管理')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 初始化
    subparsers.add_parser('init', help='初始化系统')
    
    # 扫描
    scan_parser = subparsers.add_parser('scan', help='扫描视频')
    scan_parser.add_argument('path', help='视频路径')
    scan_parser.add_argument('--mode', choices=['simple', 'fast', 'deep'], default='fast', help='扫描模式')
    scan_parser.add_argument('--incremental', action='store_true', help='增量扫描')
    scan_parser.add_argument('--protect', type=int, default=100, help='硬盘保护GB(0关闭)')
    scan_parser.add_argument('--rest', type=int, default=10, help='休息秒数')
    
    # 去重
    subparsers.add_parser('dup', help='查找重复视频')
    
    # 人物
    subparsers.add_parser('persons', help='列出所有人物')
    
    # 库管理
    lib_parser = subparsers.add_parser('lib', help='库管理')
    lib_sub = lib_parser.add_subparsers(dest='lib_cmd')
    lib_sub.add_parser('list', help='列出所有库')
    add_parser = lib_sub.add_parser('add', help='添加库')
    add_parser.add_argument('path', help='库路径')
    rm_parser = lib_sub.add_parser('rm', help='删除库')
    rm_parser.add_argument('path', help='库路径')
    
    # Web界面
    web_parser = subparsers.add_parser('web', help='启动Web界面')
    web_parser.add_argument('--port', type=int, default=5000, help='端口号')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 执行命令
    if args.command == 'init':
        数据目录.mkdir(exist_ok=True)
        with 数据库() as db:
            pass  # 数据库已自动初始化
        print("✅ 系统初始化完成")
    
    elif args.command == 'scan':
        processor = 视频处理器(模式=args.mode)
        result = processor.扫描(
            [args.path],
            增量=args.incremental,
            硬盘保护=args.protect,
            休息秒=args.rest
        )
        print(f"\n结果: {result['videos']} 个视频, {result['persons']} 个人物")
    
    elif args.command == 'dup':
        processor = 视频处理器()
        dups = processor.查找重复()
        if dups:
            print(f"\n发现 {len(dups)} 组重复:")
            for i, dup in enumerate(dups, 1):
                print(f"\n组 {i} ({dup['count']} 个视频):")
                for f in dup['files']:
                    print(f"  - {f}")
    
    elif args.command == 'persons':
        with 数据库() as db:
            persons = db.获取所有人物()
        print(f"\n👤 人物列表 ({len(persons)} 个):")
        for p in persons:
            print(f"  - {p['name']}")
    
    elif args.command == 'lib':
        mgr = 库管理器()
        if args.lib_cmd == 'list':
            mgr.列出库()
        elif args.lib_cmd == 'add':
            mgr.添加库(args.path)
        elif args.lib_cmd == 'rm':
            mgr.删除库(args.path)
        else:
            lib_parser.print_help()
    
    elif args.command == 'web':
        启动Web界面(args.port)

if __name__ == '__main__':
    main()
