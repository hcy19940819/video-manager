#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 视频管家 v4.0 - AI-Native 架构

核心特性：
- 🤖 自然语言命令系统
- 🧠 Kimi API 智能交互
- 💬 AI对话界面
- 🔍 多层pHash去重
- 👤 花名册人脸识别

作者：基于 v3.0 进化
"""

import os
import sys
import json
import sqlite3
import hashlib
import argparse
import time
import re
import base64
import threading
import queue
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Set, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import concurrent.futures
import itertools
import requests

# ============ 可选依赖 ============
try:
    from tqdm import tqdm
    有进度条 = True
except ImportError:
    有进度条 = False
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.it = iterable
            self.total = total
            self.desc = desc
            self.n = 0
            if desc: print(f"{desc}...")
        def __iter__(self): 
            for x in self.it or []: 
                yield x
                self.n += 1
        def update(self, n=1): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

try:
    import cv2
    import numpy as np
    from PIL import Image
    有视频处理 = True
except ImportError:
    有视频处理 = False

try:
    import insightface
    有人脸识别 = True
except ImportError:
    有人脸识别 = False

# ============ 全局配置 ============
视频后缀 = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', 
            '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'}

# pHash 阈值
阈值_快速 = 5
阈值_详细 = 10
阈值_相似 = 0.85

# 采样配置
快速采样间隔 = 30
详细关键帧最小 = 5
详细关键帧最大 = 20

项目目录 = Path(__file__).parent
数据目录 = 项目目录 / "data"
人脸库目录 = 数据目录 / "faces"
截图目录 = 数据目录 / "screenshots"
缩略图目录 = 数据目录 / "thumbnails"

# 确保目录存在
for d in [数据目录, 人脸库目录, 截图目录, 缩略图目录]:
    d.mkdir(exist_ok=True)

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
    详细哈希: List[str] = None
    文件哈希: str = ""
    创建时间: str = ""
    扫描版本: int = 1
    
    def __post_init__(self):
        if self.详细哈希 is None:
            self.详细哈希 = []
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()

@dataclass
class 人物特征:
    名字: str
    特征向量: List[float]
    来源视频: str
    创建时间: str = ""
    
    def __post_init__(self):
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()

@dataclass
class 人物出现:
    视频路径: str
    人物名: str
    时间点: List[float]
    置信度: float
    截图路径: str = ""
    创建时间: str = ""
    
    def __post_init__(self):
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()

@dataclass
class 视频库:
    路径: str
    名称: str = ""
    状态: str = "未分类"
    人物: List[str] = None
    视频数: int = 0
    总大小: int = 0
    总时长: float = 0.0
    扫描时间: str = ""
    创建时间: str = ""
    
    def __post_init__(self):
        if self.人物 is None: self.人物 = []
        if not self.名称: self.名称 = Path(self.路径).name
        if not self.创建时间: self.创建时间 = datetime.now().isoformat()

@dataclass
class 视频记录:
    """视频完整记录"""
    路径: str
    名称: str = ""
    大小: int = 0
    时长: float = 0.0
    宽度: int = 0
    高度: int = 0
    修改时间: float = 0.0
    拍摄日期: str = ""
    标签: List[str] = None
    人物: List[str] = None
    缩略图: str = ""
    重复组: int = 0
    
    def __post_init__(self):
        if self.标签 is None: self.标签 = []
        if self.人物 is None: self.人物 = []
        if not self.名称: self.名称 = Path(self.路径).name

# ============ 数据库管理（v4.0 增强版） ============
class 数据库:
    """统一数据库管理 - v4.0 增强"""
    
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or 数据目录 / "video_master.db")
        self.conn.row_factory = sqlite3.Row
        self.初始化()
    
    def 初始化(self):
        cursor = self.conn.cursor()
        
        # 视频指纹表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                size INTEGER,
                mtime REAL,
                duration REAL DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                fps REAL DEFAULT 0,
                quick_hash TEXT,
                detail_hashes TEXT,
                file_hash TEXT,
                created TEXT,
                tags TEXT DEFAULT '[]',
                thumbnail TEXT DEFAULT ''
            )
        ''')
        
        # 人物特征表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS person_features (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                feature TEXT,
                source_video TEXT,
                created TEXT,
                avatar TEXT DEFAULT ''
            )
        ''')
        
        # 人物出现记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS person_appearances (
                id INTEGER PRIMARY KEY,
                video_path TEXT NOT NULL,
                person_name TEXT NOT NULL,
                timestamps TEXT,
                confidence REAL,
                screenshot TEXT,
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
                persons TEXT,
                video_count INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                total_duration REAL DEFAULT 0,
                scanned TEXT,
                created TEXT
            )
        ''')
        
        # v4.0 新增：对话历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT DEFAULT '',
                created TEXT
            )
        ''')
        
        # v4.0 新增：任务队列表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_queue (
                id INTEGER PRIMARY KEY,
                task_type TEXT NOT NULL,
                params TEXT,
                status TEXT DEFAULT 'pending',
                result TEXT,
                created TEXT,
                started TEXT,
                completed TEXT
            )
        ''')
        
        # v4.0 新增：重复组表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS duplicate_groups (
                id INTEGER PRIMARY KEY,
                group_type TEXT NOT NULL,
                similarity REAL DEFAULT 1.0,
                files TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created TEXT
            )
        ''')
        
        # 索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_quick ON fingerprints(quick_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_size ON fingerprints(size)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_tags ON fingerprints(tags)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_person_name ON person_features(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_appearance_name ON person_appearances(person_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_appearance_video ON person_appearances(video_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_lib_status ON libraries(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_status ON task_queue(status)')
        
        self.conn.commit()
    
    # ============ 指纹操作 ============
    def 保存指纹(self, fp: 视频指纹):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO fingerprints 
            (path, size, mtime, duration, width, height, fps, quick_hash, detail_hashes, file_hash, created)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (fp.路径, fp.大小, fp.修改时间, fp.时长, fp.宽度, fp.高度, fp.帧率,
              fp.快速哈希, json.dumps(fp.详细哈希), fp.文件哈希, fp.创建时间))
        self.conn.commit()
    
    def 获取所有指纹(self) -> List[视频指纹]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints')
        rows = cursor.fetchall()
        return [视频指纹(
            路径=r['path'], 大小=r['size'], 修改时间=r['mtime'],
            时长=r['duration'], 宽度=r['width'], 高度=r['height'], 帧率=r['fps'],
            快速哈希=r['quick_hash'] or '',
            详细哈希=json.loads(r['detail_hashes']) if r['detail_hashes'] else [],
            文件哈希=r['file_hash'] or '', 创建时间=r['created'] or ''
        ) for r in rows]
    
    def 获取已有路径(self) -> Set[str]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT path FROM fingerprints')
        return {r[0] for r in cursor.fetchall()}
    
    def 获取视频记录(self, 路径: str = None, 限制: int = None) -> List[Dict]:
        """获取视频完整记录（含人物）"""
        cursor = self.conn.cursor()
        if 路径:
            cursor.execute('SELECT * FROM fingerprints WHERE path = ?', (路径,))
        else:
            query = 'SELECT * FROM fingerprints ORDER BY created DESC'
            if 限制:
                query += f' LIMIT {限制}'
            cursor.execute(query)
        
        rows = cursor.fetchall()
        结果 = []
        
        for r in rows:
            record = {
                'id': r['id'],
                'path': r['path'],
                'name': Path(r['path']).name,
                'size': r['size'],
                'duration': r['duration'],
                'width': r['width'],
                'height': r['height'],
                'fps': r['fps'],
                'mtime': r['mtime'],
                'created': r['created'],
                'tags': json.loads(r['tags']) if r['tags'] else [],
                'thumbnail': r['thumbnail'] or '',
                'persons': []
            }
            
            # 获取人物
            cursor.execute('SELECT person_name, timestamps FROM person_appearances WHERE video_path = ?', (r['path'],))
            for pa in cursor.fetchall():
                record['persons'].append({
                    'name': pa['person_name'],
                    'timestamps': json.loads(pa['timestamps']) if pa['timestamps'] else []
                })
            
            结果.append(record)
        
        return 结果
    
    def 搜索视频(self, 条件: Dict) -> List[Dict]:
        """多条件搜索视频"""
        cursor = self.conn.cursor()
        
        查询条件 = []
        参数 = []
        
        if '人物' in 条件:
            # 先找到包含这些人物的视频
            persons = 条件['人物'] if isinstance(条件['人物'], list) else [条件['人物']]
            placeholders = ','.join(['?' for _ in persons])
            cursor.execute(f'''
                SELECT DISTINCT video_path FROM person_appearances 
                WHERE person_name IN ({placeholders})
            ''', persons)
            视频路径 = [r[0] for r in cursor.fetchall()]
            if 视频路径:
                placeholders = ','.join(['?' for _ in 视频路径])
                查询条件.append(f"path IN ({placeholders})")
                参数.extend(视频路径)
            else:
                return []
        
        if '日期范围' in 条件:
            开始, 结束 = 条件['日期范围']
            查询条件.append("created BETWEEN ? AND ?")
            参数.extend([开始, 结束])
        
        if '路径包含' in 条件:
            查询条件.append("path LIKE ?")
            参数.append(f"%{条件['路径包含']}%")
        
        if '最小时长' in 条件:
            查询条件.append("duration >= ?")
            参数.append(条件['最小时长'])
        
        if '最大时长' in 条件:
            查询条件.append("duration <= ?")
            参数.append(条件['最大时长'])
        
        sql = 'SELECT * FROM fingerprints'
        if 查询条件:
            sql += ' WHERE ' + ' AND '.join(查询条件)
        sql += ' ORDER BY created DESC'
        
        if '限制' in 条件:
            sql += f' LIMIT {条件["限制"]}'
        
        cursor.execute(sql, 参数)
        rows = cursor.fetchall()
        
        return [{
            'id': r['id'],
            'path': r['path'],
            'name': Path(r['path']).name,
            'size': r['size'],
            'duration': r['duration'],
            'width': r['width'],
            'height': r['height'],
            'created': r['created'],
            'persons': []
        } for r in rows]
    
    # ============ 人物操作 ============
    def 保存人物特征(self, pf: 人物特征):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO person_features (name, feature, source_video, created)
            VALUES (?, ?, ?, ?)
        ''', (pf.名字, json.dumps(pf.特征向量), pf.来源视频, pf.创建时间))
        self.conn.commit()
    
    def 获取人物特征(self, name: str = None) -> List[人物特征]:
        cursor = self.conn.cursor()
        if name:
            cursor.execute('SELECT * FROM person_features WHERE name = ?', (name,))
        else:
            cursor.execute('SELECT * FROM person_features')
        return [人物特征(
            名字=r['name'], 特征向量=json.loads(r['feature']),
            来源视频=r['source_video'], 创建时间=r['created']
        ) for r in cursor.fetchall()]
    
    def 获取花名册人物(self) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT DISTINCT name FROM person_features')
        return [r[0] for r in cursor.fetchall()]
    
    def 获取花名册统计(self) -> List[Dict]:
        """获取花名册统计信息"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT name, source_video, created FROM person_features')
        人物统计 = defaultdict(lambda: {'count': 0, 'sources': set(), 'created': ''})
        
        for r in cursor.fetchall():
            人物统计[r['name']]['count'] += 1
            人物统计[r['name']]['sources'].add(r['source_video'])
            人物统计[r['name']]['created'] = r['created']
        
        return [{
            'name': name,
            'feature_count': data['count'],
            'sources': list(data['sources']),
            'created': data['created']
        } for name, data in 人物统计.items()]
    
    def 删除人物特征(self, name: str):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM person_features WHERE name = ?', (name,))
        self.conn.commit()
    
    def 保存人物出现(self, pa: 人物出现):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO person_appearances 
            (video_path, person_name, timestamps, confidence, screenshot, created)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (pa.视频路径, pa.人物名, json.dumps(pa.时间点), 
              pa.置信度, pa.截图路径, pa.创建时间))
        self.conn.commit()
    
    def 搜索人物出现(self, name: str) -> List[人物出现]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM person_appearances WHERE person_name = ?', (name,))
        return [人物出现(
            视频路径=r['video_path'], 人物名=r['person_name'],
            时间点=json.loads(r['timestamps']), 置信度=r['confidence'],
            截图路径=r['screenshot'] or '', 创建时间=r['created']
        ) for r in cursor.fetchall()]
    
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
        return [视频库(
            路径=r['path'], 名称=r['name'], 状态=r['状态'],
            人物=json.loads(r['persons']) if r['persons'] else [],
            视频数=r['video_count'], 总大小=r['total_size'],
            总时长=r['total_duration'], 扫描时间=r['scanned'] or '',
            创建时间=r['created'] or ''
        ) for r in cursor.fetchall()]
    
    def 删除库(self, path: str):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM libraries WHERE path = ?', (path,))
        self.conn.commit()
    
    # ============ 对话历史操作 ============
    def 保存对话(self, session_id: str, role: str, content: str, intent: str = ''):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO chat_history (session_id, role, content, intent, created)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, role, content, intent, datetime.now().isoformat()))
        self.conn.commit()
    
    def 获取对话历史(self, session_id: str, 限制: int = 10) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM chat_history 
            WHERE session_id = ? 
            ORDER BY created DESC LIMIT ?
        ''', (session_id, 限制))
        rows = cursor.fetchall()
        return [{
            'role': r['role'],
            'content': r['content'],
            'intent': r['intent'],
            'created': r['created']
        } for r in reversed(rows)]
    
    def 清空对话(self, session_id: str):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM chat_history WHERE session_id = ?', (session_id,))
        self.conn.commit()
    
    # ============ 任务队列操作 ============
    def 添加任务(self, task_type: str, params: Dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO task_queue (task_type, params, status, created)
            VALUES (?, ?, 'pending', ?)
        ''', (task_type, json.dumps(params), datetime.now().isoformat()))
        self.conn.commit()
        return cursor.lastrowid
    
    def 获取待处理任务(self) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM task_queue WHERE status = 'pending' 
            ORDER BY created ASC LIMIT 1
        ''')
        r = cursor.fetchone()
        if r:
            return {
                'id': r['id'],
                'type': r['task_type'],
                'params': json.loads(r['params']),
                'created': r['created']
            }
        return None
    
    def 更新任务状态(self, task_id: int, status: str, result: Dict = None):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        if status == 'running':
            cursor.execute('UPDATE task_queue SET status = ?, started = ? WHERE id = ?',
                          (status, now, task_id))
        elif status in ['completed', 'failed']:
            cursor.execute('UPDATE task_queue SET status = ?, result = ?, completed = ? WHERE id = ?',
                          (status, json.dumps(result) if result else '', now, task_id))
        self.conn.commit()
    
    # ============ 重复组操作 ============
    def 保存重复组(self, group_type: str, similarity: float, files: List[str]) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO duplicate_groups (group_type, similarity, files, created)
            VALUES (?, ?, ?, ?)
        ''', (group_type, similarity, json.dumps(files), datetime.now().isoformat()))
        self.conn.commit()
        return cursor.lastrowid
    
    def 获取重复组(self, status: str = None) -> List[Dict]:
        cursor = self.conn.cursor()
        if status:
            cursor.execute('SELECT * FROM duplicate_groups WHERE status = ? ORDER BY created DESC', (status,))
        else:
            cursor.execute('SELECT * FROM duplicate_groups ORDER BY created DESC')
        
        return [{
            'id': r['id'],
            'type': r['group_type'],
            'similarity': r['similarity'],
            'files': json.loads(r['files']),
            'status': r['status'],
            'created': r['created']
        } for r in cursor.fetchall()]
    
    def 更新重复组状态(self, group_id: int, status: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE duplicate_groups SET status = ? WHERE id = ?', (status, group_id))
        self.conn.commit()
    
    # ============ 统计 ============
    def 获取统计(self) -> Dict:
        cursor = self.conn.cursor()
        
        stats = {}
        
        cursor.execute('SELECT COUNT(*) FROM fingerprints')
        stats['videos'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM person_features')
        stats['person_features'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT person_name) FROM person_appearances')
        stats['persons'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT name) FROM person_features')
        stats['roster'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM libraries')
        stats['libraries'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM duplicate_groups WHERE status = "pending"')
        stats['duplicates'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(size) FROM fingerprints')
        result = cursor.fetchone()[0]
        stats['total_size'] = result or 0
        
        cursor.execute('SELECT SUM(duration) FROM fingerprints')
        result = cursor.fetchone()[0]
        stats['total_duration'] = result or 0
        
        return stats
    
    def 关闭(self):
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.关闭()


# ============ 任务队列管理器 ============
class 任务管理器:
    """异步任务管理 - v4.0 Phase 3"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.任务队列 = queue.Queue()
        self.任务状态 = {}  # task_id -> {status, progress, result, error}
        self.执行线程 = None
        self.运行中 = False
        self.当前任务 = None
    
    def 启动(self):
        """启动任务处理线程"""
        if not self.运行中:
            self.运行中 = True
            self.执行线程 = threading.Thread(target=self._处理循环, daemon=True)
            self.执行线程.start()
            print("✓ 任务队列已启动")
    
    def 停止(self):
        """停止任务处理"""
        self.运行中 = False
        if self.执行线程:
            self.执行线程.join(timeout=5)
    
    def _处理循环(self):
        """后台任务处理循环"""
        while self.运行中:
            try:
                task = self.任务队列.get(timeout=1)
                self._执行任务(task)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"任务处理错误: {e}")
    
    def _执行任务(self, task):
        """执行单个任务"""
        task_id = task['id']
        task_type = task['type']
        params = task['params']
        
        self.当前任务 = task_id
        self.更新任务状态(task_id, 'running', progress=0)
        
        try:
            if task_type == 'scan':
                result = self._执行扫描(params, task_id)
            elif task_type == 'learn':
                result = self._执行学习(params, task_id)
            elif task_type == 'dedup':
                result = self._执行去重(params, task_id)
            elif task_type == 'thumbnail':
                result = self._执行缩略图生成(params, task_id)
            else:
                result = {'error': f'未知任务类型: {task_type}'}
            
            self.更新任务状态(task_id, 'completed', result=result, progress=100)
            
        except Exception as e:
            self.更新任务状态(task_id, 'failed', error=str(e))
        
        self.当前任务 = None
    
    def _执行扫描(self, params, task_id):
        """执行扫描任务"""
        路径 = params.get('path', '')
        模式 = params.get('mode', 'fast')
        
        处理器 = 视频处理器(模式=模式)
        
        # 收集视频
        所有视频 = []
        for p in [路径]:
            所有视频.extend(处理器._收集视频(p))
        
        total = len(所有视频)
        processed = 0
        
        with 数据库() as db:
            已有 = db.获取已有路径()
        
        新增视频 = [v for v in 所有视频 if v not in 已有]
        
        for 视频路径 in 新增视频:
            try:
                处理器._处理单个视频(视频路径, 数据库())
                processed += 1
                progress = int(processed / len(新增视频) * 100) if 新增视频 else 100
                self.更新任务状态(task_id, 'running', progress=progress, 
                                result={'processed': processed, 'total': len(新增视频)})
            except Exception as e:
                print(f"处理失败 {视频路径}: {e}")
        
        return {
            'videos': total,
            'new': len(新增视频),
            'processed': processed
        }
    
    def _执行学习(self, params, task_id):
        """执行学习任务"""
        name = params.get('name', '')
        path = params.get('path', '')
        
        p = Path(path)
        视频列表 = []
        for ext in 视频后缀:
            视频列表.extend(p.rglob(f"*{ext}"))
        
        特征计数 = 0
        成功视频 = 0
        
        处理器 = 视频处理器(模式='深度', 启用花名册=False)
        
        for i, 视频路径 in enumerate(视频列表):
            try:
                if not 有人脸识别:
                    break
                
                cap = cv2.VideoCapture(str(视频路径))
                if not cap.isOpened():
                    continue
                
                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                总帧数 = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                时长 = 总帧数 / fps if fps > 0 else 0
                采样点 = [时长 * i / 5 for i in range(1, 5)]
                
                for 时间点 in 采样点:
                    帧位置 = int(时间点 * fps)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 帧位置)
                    ret, frame = cap.read()
                    
                    if ret and frame is not None:
                        faces = 处理器.人脸检测.get(frame)
                        for face in faces:
                            if face.det_score >= 0.7:
                                特征 = face.embedding.tolist()
                                with 数据库() as db:
                                    db.保存人物特征(人物特征(
                                        名字=name, 特征向量=特征, 
                                        来源视频=str(视频路径)
                                    ))
                                特征计数 += 1
                
                cap.release()
                成功视频 += 1
                
                progress = int((i + 1) / len(视频列表) * 100)
                self.更新任务状态(task_id, 'running', progress=progress,
                                result={'videos': i + 1, 'total': len(视频列表), 'features': 特征计数})
                
            except Exception as e:
                print(f"学习失败 {视频路径}: {e}")
        
        return {
            'name': name,
            'videos': len(视频列表),
            'processed': 成功视频,
            'features': 特征计数
        }
    
    def _执行去重(self, params, task_id):
        """执行去重任务"""
        处理器 = 视频处理器(模式='快速')
        重复组 = 处理器.查找重复(模式='全部')
        
        with 数据库() as db:
            for 组 in 重复组:
                db.保存重复组(组['type'], 0.85, 组['files'])
        
        self.更新任务状态(task_id, 'running', progress=100)
        
        return {
            'groups': len(重复组),
            'files': sum(len(g['files']) for g in 重复组)
        }
    
    def _执行缩略图生成(self, params, task_id):
        """执行缩略图生成任务"""
        with 数据库() as db:
            视频列表 = db.获取视频记录()
        
        生成器 = 缩略图生成器()
        generated = 0
        
        for i, v in enumerate(视频列表):
            try:
                缩略图 = 生成器.生成缩略图(v['path'])
                if 缩略图:
                    generated += 1
                
                progress = int((i + 1) / len(视频列表) * 100)
                self.更新任务状态(task_id, 'running', progress=progress,
                                result={'generated': generated, 'total': len(视频列表)})
            except Exception as e:
                print(f"缩略图生成失败 {v['path']}: {e}")
        
        return {
            'total': len(视频列表),
            'generated': generated
        }
    
    def 提交任务(self, task_type: str, params: Dict) -> str:
        """提交新任务"""
        task_id = f"{task_type}_{int(time.time() * 1000)}"
        
        task = {
            'id': task_id,
            'type': task_type,
            'params': params,
            'created': datetime.now().isoformat()
        }
        
        self.任务状态[task_id] = {
            'status': 'pending',
            'progress': 0,
            'result': None,
            'error': None,
            'created': task['created']
        }
        
        self.任务队列.put(task)
        
        # 保存到数据库
        with 数据库() as db:
            db.添加任务(task_type, params)
        
        return task_id
    
    def 更新任务状态(self, task_id: str, status: str, progress: int = None, 
                    result: Dict = None, error: str = None):
        """更新任务状态"""
        if task_id in self.任务状态:
            self.任务状态[task_id]['status'] = status
            if progress is not None:
                self.任务状态[task_id]['progress'] = progress
            if result is not None:
                self.任务状态[task_id]['result'] = result
            if error is not None:
                self.任务状态[task_id]['error'] = error
    
    def 获取任务状态(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        return self.任务状态.get(task_id)
    
    def 获取所有任务(self) -> List[Dict]:
        """获取所有任务状态"""
        return [
            {'id': k, **v} 
            for k, v in sorted(self.任务状态.items(), 
                              key=lambda x: x[1].get('created', ''), 
                              reverse=True)
        ]
    
    def 获取当前任务(self) -> Optional[Dict]:
        """获取当前正在执行的任务"""
        if self.当前任务:
            return self.获取任务状态(self.当前任务)
        return None


# ============ pHash 工具 ============
class pHash工具:
    """感知哈希工具"""
    
    @staticmethod
    def 计算phash(图像) -> str:
        """计算pHash（64位）"""
        if 图像 is None:
            return ""
        
        try:
            if len(图像.shape) == 3:
                灰度 = cv2.cvtColor(图像, cv2.COLOR_BGR2GRAY)
            else:
                灰度 = 图像
            
            小图 = cv2.resize(灰度, (32, 32))
            dct = cv2.dct(np.float32(小图))
            dct_low = dct[:8, :8]
            avg = (dct_low.sum() - dct_low[0,0]) / 63
            bits = (dct_low > avg).flatten()
            return ''.join(['1' if b else '0' for b in bits])
        except:
            return ""
    
    @staticmethod
    def 汉明距离(哈希1: str, 哈希2: str) -> int:
        """计算汉明距离"""
        if not 哈希1 or not 哈希2 or len(哈希1) != len(哈希2):
            return 999
        return sum(c1 != c2 for c1, c2 in zip(哈希1, 哈希2))


# ============ 缩略图生成器 ============
class 缩略图生成器:
    """视频缩略图生成与管理"""
    
    def __init__(self, 缩略图目录: Path = None):
        self.缩略图目录 = 缩略图目录 or Path(__file__).parent / "data" / "thumbnails"
        self.缩略图目录.mkdir(parents=True, exist_ok=True)
        self.默认尺寸 = (320, 180)  # 16:9
    
    def 生成缩略图(self, 视频路径: str, 时间点: float = None) -> Optional[str]:
        """为视频生成缩略图，返回缩略图路径"""
        if not 有视频处理:
            return None
        
        try:
            # 生成唯一文件名
            路径哈希 = hashlib.md5(视频路径.encode()).hexdigest()[:16]
            缩略图路径 = self.缩略图目录 / f"{路径哈希}.jpg"
            
            # 如果已存在且不超时，直接返回
            if 缩略图路径.exists():
                return str(缩略图路径)
            
            cap = cv2.VideoCapture(视频路径)
            if not cap.isOpened():
                return None
            
            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            总帧数 = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            时长 = 总帧数 / fps if fps > 0 else 0
            
            # 选择时间点（默认中间）
            if 时间点 is None:
                时间点 = 时长 / 2
            
            # 定位到指定时间
            帧位置 = int(时间点 * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, 帧位置)
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                return None
            
            # 调整大小
            frame = cv2.resize(frame, self.默认尺寸)
            
            # 保存为JPEG
            cv2.imwrite(str(缩略图路径), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            return str(缩略图路径)
            
        except Exception as e:
            print(f"生成缩略图失败 {视频路径}: {e}")
            return None
    
    def 获取缩略图(self, 视频路径: str) -> Optional[str]:
        """获取视频缩略图路径，不存在则生成"""
        return self.生成缩略图(视频路径)
    
    def 批量生成(self, 视频路径列表: List[str], 进度回调=None) -> Dict[str, str]:
        """批量生成缩略图"""
        结果 = {}
        
        for i, 路径 in enumerate(视频路径列表):
            缩略图 = self.生成缩略图(路径)
            if 缩略图:
                结果[路径] = 缩略图
            
            if 进度回调:
                进度回调(i + 1, len(视频路径列表))
        
        return 结果
    
    def 清理过期(self, 保留天数: int = 30):
        """清理长时间未使用的缩略图"""
        现在 = datetime.now()
        删除计数 = 0
        
        for 文件 in self.缩略图目录.glob("*.jpg"):
            修改时间 = datetime.fromtimestamp(文件.stat().st_mtime)
            if (现在 - 修改时间).days > 保留天数:
                文件.unlink()
                删除计数 += 1
        
        return 删除计数
    
    def 获取视频关键帧(self, 视频路径: str, 时间点列表: List[float]) -> List[Dict]:
        """获取视频在多个时间点的帧"""
        if not 有视频处理:
            return []
        
        try:
            cap = cv2.VideoCapture(视频路径)
            if not cap.isOpened():
                return []
            
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            结果 = []
            
            for 时间点 in 时间点列表:
                帧位置 = int(时间点 * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, 帧位置)
                
                ret, frame = cap.read()
                if ret and frame is not None:
                    # 编码为base64
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    图片数据 = base64.b64encode(buffer).decode('utf-8')
                    
                    结果.append({
                        'time': 时间点,
                        'image': f"data:image/jpeg;base64,{图片数据}"
                    })
            
            cap.release()
            return 结果
            
        except Exception as e:
            print(f"获取关键帧失败: {e}")
            return []


# ============ 视频处理器 ============
class 视频处理器:
    """视频处理核心"""
    
    def __init__(self, 模式: str = "快速", 启用花名册: bool = False):
        self.模式 = 模式
        self.启用花名册 = 启用花名册
        self.人脸检测 = None
        self.phash工具 = pHash工具()
        
        if 有人脸识别 and 模式 != "简单":
            try:
                self.人脸检测 = insightface.app.FaceAnalysis()
                self.人脸检测.prepare(ctx_id=-1, det_size=(640, 640))
                print("✓ AI模型加载成功")
            except Exception as e:
                print(f"✗ AI模型加载失败: {e}")
    
    def 扫描(self, 路径列表: List[str], 增量: bool = True,
             硬盘保护: int = 100, 休息秒: int = 10) -> Dict:
        """扫描视频"""
        print(f"\n{'='*60}")
        print(f"🎬 开始扫描 [模式: {self.模式}]")
        print(f"{'='*60}")
        
        所有视频 = []
        for p in 路径列表:
            所有视频.extend(self._收集视频(p))
        
        if not 所有视频:
            print("未找到视频")
            return {'videos': 0, 'fingerprints': 0, 'persons': 0}
        
        print(f"发现 {len(所有视频)} 个视频")
        
        if 增量:
            with 数据库() as db:
                已有 = db.获取已有路径()
            所有视频 = [v for v in 所有视频 if v not in 已有]
            print(f"新增视频: {len(所有视频)} 个")
        
        if not 所有视频:
            return {'videos': 0, 'fingerprints': 0, 'persons': 0}
        
        批量大小 = 硬盘保护 * 1024**3 if 硬盘保护 > 0 else float('inf')
        已处理大小 = 0
        休息次数 = 0
        
        视频计数 = 0
        指纹计数 = 0
        人物计数 = 0
        
        迭代器 = tqdm(所有视频, desc="处理视频") if 有进度条 else 所有视频
        
        with 数据库() as db:
            for 路径 in 迭代器:
                try:
                    结果 = self._处理单个视频(路径, db)
                    视频计数 += 1
                    指纹计数 += 结果.get('fingerprints', 0)
                    人物计数 += 结果.get('persons', 0)
                    
                    文件大小 = Path(路径).stat().st_size
                    已处理大小 += 文件大小
                    
                    if 硬盘保护 > 0 and 已处理大小 >= 批量大小:
                        self._休息(休息秒)
                        已处理大小 = 0
                        休息次数 += 1
                        
                except Exception as e:
                    print(f"✗ {Path(路径).name}: {e}")
        
        return {
            'videos': 视频计数,
            'fingerprints': 指纹计数,
            'persons': 人物计数,
            'rests': 休息次数
        }
    
    def _收集视频(self, 路径: str) -> List[str]:
        """收集目录下所有视频"""
        p = Path(路径)
        if p.is_file() and p.suffix.lower() in 视频后缀:
            return [str(p.absolute())]
        
        results = []
        for ext in 视频后缀:
            results.extend(str(f.absolute()) for f in p.rglob(f"*{ext}"))
        return results
    
    def _处理单个视频(self, 路径: str, db: 数据库) -> Dict:
        """处理单个视频"""
        stat = Path(路径).stat()
        fp = 视频指纹(路径=路径, 大小=stat.st_size, 修改时间=stat.st_mtime)
        
        人物计数 = 0
        
        if 有视频处理:
            cap = cv2.VideoCapture(路径)
            if cap.isOpened():
                fp.帧率 = cap.get(cv2.CAP_PROP_FPS)
                fp.宽度 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                fp.高度 = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                总帧数 = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                fp.时长 = 总帧数 / fp.帧率 if fp.帧率 > 0 else 0
                
                fp.快速哈希 = self._计算快速phash(cap)
                fp.详细哈希 = self._计算详细phash(cap, 总帧数)
                fp.文件哈希 = self._计算md5(路径)
                
                if self.人脸检测 and self.模式 != "简单":
                    人物列表 = self._识别人物(cap, 路径, db)
                    人物计数 = len(人物列表)
                
                cap.release()
        
        db.保存指纹(fp)
        return {'fingerprints': 1, 'persons': 人物计数}
    
    def _计算快速phash(self, cap) -> str:
        """计算快速pHash"""
        if not cap or not cap.isOpened():
            return ""
        
        try:
            总帧数 = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.set(cv2.CAP_PROP_POS_FRAMES, 总帧数 / 2)
            ret, frame = cap.read()
            if ret:
                return self.phash工具.计算phash(frame)
        except:
            pass
        return ""
    
    def _计算详细phash(self, cap, 总帧数: float) -> List[str]:
        """计算详细pHash序列"""
        if not cap or not cap.isOpened() or 总帧数 <= 0:
            return []
        
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            间隔 = int(fps * 快速采样间隔)
            关键帧数 = min(max(int(总帧数 / 间隔), 详细关键帧最小), 详细关键帧最大)
            步长 = int(总帧数 / (关键帧数 + 1))
            
            哈希列表 = []
            for i in range(1, 关键帧数 + 1):
                帧位置 = i * 步长
                if 帧位置 >= 总帧数:
                    break
                
                cap.set(cv2.CAP_PROP_POS_FRAMES, 帧位置)
                ret, frame = cap.read()
                if ret:
                    phash = self.phash工具.计算phash(frame)
                    if phash:
                        哈希列表.append(phash)
            
            return 哈希列表
        except:
            return []
    
    def _计算md5(self, 路径: str) -> str:
        """计算文件前1MB的MD5"""
        try:
            h = hashlib.md5()
            with open(路径, 'rb') as f:
                h.update(f.read(1024 * 1024))
            return h.hexdigest()[:16]
        except:
            return ""
    
    def _识别人物(self, cap, 路径: str, db: 数据库) -> List[人物出现]:
        """识别人物"""
        if not cap or not cap.isOpened():
            return []
        
        if self.模式 == "深度":
            间隔秒 = 3
            最大帧 = 50
        else:
            间隔秒 = 10
            最大帧 = 10
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        帧间隔 = int(fps * 间隔秒)
        总帧数 = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        人脸数据 = defaultdict(lambda: {'times': [], 'conf': [], 'features': []})
        
        for i in range(0, min(总帧数, 帧间隔 * 最大帧), 帧间隔):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret:
                break
            
            时间点 = i / fps
            faces = self.人脸检测.get(frame)
            
            for face in faces:
                if face.det_score < 0.7:
                    continue
                
                特征 = face.embedding.tolist()
                
                if self.启用花名册:
                    匹配结果 = self._匹配花名册(特征, db)
                    if 匹配结果:
                        名字, 置信度 = 匹配结果
                        人脸数据[名字]['times'].append(时间点)
                        人脸数据[名字]['conf'].append(置信度)
                else:
                    face_id = f"face_{hash(tuple(特征[:5])) % 10000}"
                    人脸数据[face_id]['times'].append(时间点)
                    人脸数据[face_id]['conf'].append(float(face.det_score))
                    人脸数据[face_id]['features'].append(特征)
        
        记录列表 = []
        for 名字, 数据 in 人脸数据.items():
            if len(数据['times']) >= 2:
                pa = 人物出现(
                    视频路径=路径,
                    人物名=名字,
                    时间点=sorted(数据['times']),
                    置信度=sum(数据['conf']) / len(数据['conf'])
                )
                db.保存人物出现(pa)
                记录列表.append(pa)
        
        return 记录列表
    
    def _匹配花名册(self, 特征, db: 数据库) -> Optional[Tuple[str, float]]:
        """匹配花名册"""
        花名册 = db.获取人物特征()
        if not 花名册:
            return None
        
        最佳匹配 = None
        最高相似 = 0.0
        
        for pf in 花名册:
            相似 = self._余弦相似度(特征, pf.特征向量)
            if 相似 > 最高相似 and 相似 > 0.6:
                最高相似 = 相似
                最佳匹配 = pf.名字
        
        return (最佳匹配, 最高相似) if 最佳匹配 else None
    
    def _余弦相似度(self, a, b) -> float:
        """余弦相似度"""
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    
    def _休息(self, seconds: int):
        """硬盘保护休息"""
        print(f"\n💤 硬盘保护: 休息 {seconds} 秒...")
        for i in range(seconds, 0, -1):
            print(f"   剩余 {i} 秒...", end='\r')
            time.sleep(1)
        print("   继续扫描!         ")
    
    def 查找重复(self, 模式: str = "全部") -> List[Dict]:
        """查找重复视频"""
        print("\n🔍 查找重复视频...")
        
        with 数据库() as db:
            指纹列表 = db.获取所有指纹()
        
        if not 指纹列表:
            print("视频库为空")
            return []
        
        重复组 = []
        已处理 = set()
        
        by_key = defaultdict(list)
        for fp in 指纹列表:
            if fp.时长 > 0:
                key = (fp.大小, round(fp.时长))
            else:
                key = (fp.大小,)
            by_key[key].append(fp)
        
        for key, 组 in by_key.items():
            if len(组) < 2:
                continue
            
            for i, fp1 in enumerate(组):
                if fp1.路径 in 已处理:
                    continue
                
                当前组 = [fp1]
                
                for fp2 in 组[i+1:]:
                    if fp2.路径 in 已处理:
                        continue
                    
                    相似类型 = ""
                    
                    if fp1.文件哈希 and fp1.文件哈希 == fp2.文件哈希:
                        相似类型 = "identical"
                    elif fp1.快速哈希 and fp2.快速哈希:
                        dist = self.phash工具.汉明距离(fp1.快速哈希, fp2.快速哈希)
                        if dist <= 阈值_快速:
                            相似类型 = "similar"
                        elif 模式 == "全部" and fp1.详细哈希 and fp2.详细哈希:
                            match_count = sum(
                                1 for h1, h2 in zip(fp1.详细哈希, fp2.详细哈希)
                                if self.phash工具.汉明距离(h1, h2) <= 阈值_详细
                            )
                            if match_count >= min(len(fp1.详细哈希), len(fp2.详细哈希)) * 0.5:
                                相似类型 = "maybe"
                    
                    if 相似类型:
                        当前组.append(fp2)
                        已处理.add(fp2.路径)
                
                if len(当前组) > 1:
                    已处理.add(fp1.路径)
                    重复组.append({
                        'type': 相似类型,
                        'files': [fp.路径 for fp in 当前组],
                        'count': len(当前组),
                        'size': fp1.大小
                    })
        
        print(f"发现 {len(重复组)} 组重复视频")
        return 重复组


# ============ Kimi API 客户端 ============
class Kimi客户端:
    """Kimi API 客户端 - v4.0 Phase 3.2"""
    
    API_URL = "https://api.moonshot.cn/v1/chat/completions"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get('KIMI_API_KEY', '')
        self.模型 = "moonshot-v1-8k"
    
    def 解析意图(self, 用户输入: str) -> Dict:
        """使用Kimi解析用户意图"""
        if not self.api_key:
            return None
        
        系统提示 = """你是一个视频管理助手的意图解析器。请分析用户的自然语言输入，提取意图和参数。

可用意图：
- scan: 扫描视频目录（参数：path路径, mode模式）
- dedup: 查找重复视频
- search: 搜索视频（参数：person人物, date_range日期范围, path_contains路径包含）
- person: 查看花名册
- learn: 学习人物特征（参数：name人物名称, path视频路径）
- stats: 查看统计信息
- help: 帮助
- greeting: 问候

请返回JSON格式：
{
    "intent": "意图名称",
    "params": {
        "参数名": "参数值"
    },
    "confidence": 0.95
}"""
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.模型,
                "messages": [
                    {"role": "system", "content": 系统提示},
                    {"role": "user", "content": 用户输入}
                ],
                "temperature": 0.3
            }
            
            response = requests.post(self.API_URL, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                内容 = data['choices'][0]['message']['content']
                
                # 提取JSON
                try:
                    # 尝试直接解析
                    结果 = json.loads(内容)
                except:
                    # 尝试从文本中提取JSON
                    import re
                    json_match = re.search(r'\{[^}]+\}', 内容)
                    if json_match:
                        结果 = json.loads(json_match.group())
                    else:
                        return None
                
                return 结果
            else:
                print(f"Kimi API错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Kimi API调用失败: {e}")
            return None
    
    def 生成回复(self, 意图: str, 结果: Dict, 用户输入: str) -> str:
        """使用Kimi生成自然语言回复"""
        if not self.api_key:
            return None
        
        系统提示 = """你是视频管家助手，用友好、简洁的中文回复用户。
根据意图和执行结果生成自然的回复。"""
        
        提示 = f"""用户输入: {用户输入}
意图: {意图}
执行结果: {json.dumps(结果, ensure_ascii=False)}

请生成友好、简洁的回复："""
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.模型,
                "messages": [
                    {"role": "system", "content": 系统提示},
                    {"role": "user", "content": 提示}
                ],
                "temperature": 0.7
            }
            
            response = requests.post(self.API_URL, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                return None
                
        except Exception as e:
            return None


# ============ v4.0 AI核心 ============
class 自然语言解析器:
    """自然语言命令解析器"""
    
    # 意图定义
    意图_扫描 = "scan"
    意图_去重 = "dedup"
    意图_搜索 = "search"
    意图_人物 = "person"
    意图_学习 = "learn"
    意图_统计 = "stats"
    意图_帮助 = "help"
    意图_问候 = "greeting"
    意图_未知 = "unknown"
    
    # 意图关键词映射（按优先级排序，先匹配的先检查）
    意图关键词 = {
        意图_问候: ['你好', '嗨', 'hello', 'hi', '在吗', '在不在', '您好'],
        意图_帮助: ['帮助', 'help', '怎么用', '能做什么', '说明', '文档', '教程'],
        意图_统计: ['统计', '概览', '总数', '情况', '状态', '数据', 'overview', 'stats'],
        意图_去重: ['去重', '重复', '相似', '一样的', '相同', '清理', '节省空间', 'duplicate'],
        意图_学习: ['学习', '训练', '认识', '记住', '了解', '教会', 'learn'],
        意图_扫描: ['扫描', '添加', '导入', '索引', '发现', 'scan', 'index'],
        意图_搜索: ['找', '搜索', '查询', '查', '搜索', '查找', '有没有', '包含', '筛选', '过滤', 'search', 'find'],
        意图_人物: ['人物', '花名册', '头像', '面孔', '识别', '谁', 'person'],
    }
    
    # 模式关键词
    模式关键词 = {
        'simple': ['简单', '快速', '粗略', '大概'],
        'fast': ['快速', '正常', '推荐', '默认'],
        'deep': ['深度', '详细', '完整', '全部', '彻底']
    }
    
    # 时间关键词
    时间关键词 = {
        '今天': 0,
        '昨天': 1,
        '前天': 2,
        '这周': 7,
        '上周': 14,
        '这周': 7,
        '最近': 7,
        '上周': 14,
        '这个月': 30,
        '上个月': 60,
    }
    
    def 解析(self, 文本: str) -> Dict:
        """解析自然语言命令（优先使用Kimi API）"""
        文本 = 文本.strip()
        
        # 1. 尝试使用Kimi API解析
        if kimi客户端:
            kimi结果 = kimi客户端.解析意图(文本)
            if kimi结果 and kimi结果.get('confidence', 0) > 0.7:
                print(f"✓ Kimi解析: {kimi结果.get('intent')} (置信度: {kimi结果.get('confidence')})")
                return {
                    'intent': kimi结果.get('intent', self.意图_未知),
                    'params': kimi结果.get('params', {}),
                    'raw': 文本,
                    'source': 'kimi'
                }
        
        # 2. 本地解析作为fallback
        意图 = self._识别意图(文本)
        参数 = self._提取参数(文本, 意图)
        
        return {
            'intent': 意图,
            'params': 参数,
            'raw': 文本,
            'source': 'local'
        }
    
    def _识别意图(self, 文本: str) -> str:
        """识别用户意图"""
        for 意图, 关键词列表 in self.意图关键词.items():
            for 关键词 in 关键词列表:
                if 关键词 in 文本:
                    return 意图
        return self.意图_未知
    
    def _提取参数(self, 文本: str, 意图: str) -> Dict:
        """提取命令参数"""
        参数 = {}
        
        # 提取路径
        路径匹配 = re.findall(r'["\']([^"\']+)["\']|(/[\w/\-]+)|([A-Z]:\\[\\\w\-]+)', 文本)
        if 路径匹配:
            for 匹配组 in 路径匹配:
                for 路径 in 匹配组:
                    if 路径 and (Path(路径).exists() or '/' in 路径 or '\\' in 路径):
                        参数['路径'] = 路径
                        break
        
        # 检测默认路径关键词
        if '下载' in 文本 or 'Downloads' in 文本:
            参数['路径'] = str(Path.home() / 'Downloads')
        elif '桌面' in 文本 or 'Desktop' in 文本:
            参数['路径'] = str(Path.home() / 'Desktop')
        elif '视频' in 文本 or 'Videos' in 文本:
            参数['路径'] = str(Path.home() / 'Videos')
        
        # 提取模式
        for 模式, 关键词列表 in self.模式关键词.items():
            for 关键词 in 关键词列表:
                if 关键词 in 文本:
                    参数['模式'] = 模式
                    break
        
        # 提取时间范围
        for 关键词, 天数 in self.时间关键词.items():
            if 关键词 in 文本:
                结束 = datetime.now()
                开始 = 结束 - timedelta(days=天数)
                参数['时间范围'] = (开始.isoformat(), 结束.isoformat())
                break
        
        # 特定意图参数
        if 意图 == self.意图_搜索:
            # 提取人物
            if '小宝' in 文本:
                参数['人物'] = '小宝'
            elif '爷爷' in 文本:
                参数['人物'] = '爷爷'
            elif '奶奶' in 文本:
                参数['人物'] = '奶奶'
            
            # 提取时长限制
            if '短' in 文本:
                参数['最大时长'] = 60  # 1分钟
            elif '长' in 文本:
                参数['最小时长'] = 300  # 5分钟
        
        return 参数


class AI助手:
    """AI助手核心 - v4.0"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.kimi = Kimi客户端(api_key) if api_key else None
        self.解析器 = 自然语言解析器()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def 处理(self, 用户输入: str) -> Dict:
        """处理用户输入"""
        # 1. 解析意图（优先Kimi）
        解析结果 = self.解析器.解析(用户输入, self.kimi)
        意图 = 解析结果['intent']
        参数 = 解析结果['params']
        
        # 2. 保存对话
        with 数据库() as db:
            db.保存对话(self.session_id, 'user', 用户输入, 意图)
        
        # 3. 执行对应操作
        结果 = self._执行意图(意图, 参数, 用户输入)
        
        # 4. 生成回复（优先Kimi）
        回复 = self._生成回复(意图, 结果, 参数, 用户输入)
        
        # 5. 保存AI回复
        with 数据库() as db:
            db.保存对话(self.session_id, 'assistant', 回复, 意图)
        
        return {
            'intent': 意图,
            'params': 参数,
            'result': 结果,
            'response': 回复,
            'source': 解析结果.get('source', 'local')
        }
    
    def _执行意图(self, 意图: str, 参数: Dict, 原始文本: str) -> Dict:
        """根据意图执行操作"""
        
        if 意图 == self.解析器.意图_问候:
            return {'type': 'greeting'}
        
        elif 意图 == self.解析器.意图_帮助:
            return {'type': 'help'}
        
        elif 意图 == self.解析器.意图_统计:
            with 数据库() as db:
                return {'type': 'stats', 'data': db.获取统计()}
        
        elif 意图 == self.解析器.意图_扫描:
            路径 = 参数.get('路径')
            if not 路径:
                # 列出常见视频目录
                候选 = []
                for 候选路径 in ['~/Videos', '~/Downloads', '~/Desktop']:
                    p = Path(候选路径).expanduser()
                    if p.exists():
                        候选.append(str(p))
                return {'type': 'scan_prompt', 'paths': 候选}
            
            模式 = 参数.get('模式', 'fast')
            处理器 = 视频处理器(模式=模式)
            结果 = 处理器.扫描([路径], 增量=True)
            return {'type': 'scan_result', 'data': 结果}
        
        elif 意图 == self.解析器.意图_去重:
            处理器 = 视频处理器(模式='快速')
            重复组 = 处理器.查找重复(模式='全部')
            
            # 保存到数据库
            with 数据库() as db:
                for 组 in 重复组:
                    db.保存重复组(组['type'], 0.85 if 组['type'] == 'similar' else 1.0, 组['files'])
            
            return {'type': 'dup_result', 'groups': 重复组}
        
        elif 意图 == self.解析器.意图_搜索:
            with 数据库() as db:
                视频 = db.搜索视频(参数)
            return {'type': 'search_result', 'videos': 视频, 'count': len(视频)}
        
        elif 意图 == self.解析器.意图_人物:
            with 数据库() as db:
                人物 = db.获取花名册统计()
                出现记录 = db.获取所有人物()
            return {'type': 'person_stats', 'roster': 人物, 'appearances': 出现记录}
        
        else:
            return {'type': 'unknown', 'message': '我不太明白，试试说"扫描下载文件夹"或"找重复视频"'}
    
    def _生成回复(self, 意图: str, 结果: Dict, 参数: Dict, 原始文本: str = None) -> str:
        """生成自然语言回复（优先使用Kimi）"""
        
        # 1. 尝试使用Kimi生成回复
        if self.kimi and 原始文本:
            kimi回复 = self.kimi.生成回复(意图, 结果, 原始文本)
            if kimi回复:
                return kimi回复
        
        # 2. 本地模板回复作为fallback
        类型 = 结果.get('type')
        
        if 类型 == 'greeting':
            return "你好！我是你的视频管家 🤖\n\n今天想整理什么视频？试试说：\n• 扫描下载文件夹\n• 找重复视频\n• 查看统计"
        
        elif 类型 == 'help':
            return """我可以帮你：

📁 **扫描视频**
• "扫描下载文件夹" - 索引视频文件
• "扫描 /path/to/videos --mode deep" - 深度扫描

🔍 **查找视频**
• "找上周拍的视频" - 按时间搜索
• "找包含小宝的视频" - 按人物搜索
• "找重复视频" - 识别重复文件

👤 **人物管理**
• "学习已分类文件夹里的人物" - 建立花名册
• "查看花名册" - 显示已学习的人物

📊 **查看统计**
• "查看统计" - 查看视频库概况

有什么想做的直接说！"""
        
        elif 类型 == 'stats':
            data = 结果['data']
            size_gb = data.get('total_size', 0) / (1024**3)
            hours = int(data.get('total_duration', 0) / 3600)
            
            return f"""📊 **视频库统计**

• 📹 视频总数: {data.get('videos', 0)} 个
• 💾 总大小: {size_gb:.2f} GB
• 🕐 总时长: {hours} 小时
• 👥 识别到人物: {data.get('persons', 0)} 个
• 📚 花名册: {data.get('roster', 0)} 人
• ⚠️ 待处理重复: {data.get('duplicates', 0)} 组

需要我做什么吗？"""
        
        elif 类型 == 'scan_prompt':
            paths = 结果['paths']
            if paths:
                return f"发现这些视频目录：\n" + "\n".join([f"• {p}" for p in paths]) + "\n\n要扫描哪个？直接说路径或编号。"
            return "没发现视频目录，请告诉我视频在哪里，比如：\n扫描 /home/user/视频"
        
        elif 类型 == 'scan_result':
            data = 结果['data']
            return f"✅ 扫描完成！\n\n• 新增视频: {data.get('videos', 0)} 个\n• 生成指纹: {data.get('fingerprints', 0)} 个\n• 识别人物: {data.get('persons', 0)} 个" + \
                   (f"\n• 硬盘休息: {data.get('rests', 0)} 次" if data.get('rests') else "")
        
        elif 类型 == 'dup_result':
            groups = 结果['groups']
            if not groups:
                return "✅ 未发现重复视频，你的视频库很干净！"
            
            total_size = sum(g.get('size', 0) * (g.get('count', 1) - 1) for g in groups)
            size_gb = total_size / (1024**3)
            
            回复 = f"🔍 发现 {len(groups)} 组重复视频\n"
            回复 += f"💾 预计可节省: {size_gb:.2f} GB\n\n"
            
            for i, g in enumerate(groups[:3], 1):
                类型映射 = {'identical': '完全重复', 'similar': '相似视频', 'maybe': '可能相似'}
                类型名 = 类型映射.get(g['type'], g['type'])
                回复 += f"{i}. [{类型名}] {len(g['files'])} 个文件\n"
                for f in g['files'][:2]:
                    回复 += f"   • {Path(f).name}\n"
            
            if len(groups) > 3:
                回复 += f"\n...还有 {len(groups) - 3} 组"
            
            回复 += "\n\n要查看详情或删除重复吗？"
            return 回复
        
        elif 类型 == 'search_result':
            count = 结果['count']
            videos = 结果['videos']
            
            if count == 0:
                return "没找到符合条件的视频，换个条件试试？"
            
            回复 = f"找到 {count} 个视频：\n\n"
            for v in videos[:5]:
                时长 = f"{int(v.get('duration', 0) // 60)}:{int(v.get('duration', 0) % 60):02d}"
                回复 += f"• {v['name']} ({时长})\n"
            
            if count > 5:
                回复 += f"\n...还有 {count - 5} 个"
            
            return 回复
        
        elif 类型 == 'person_stats':
            roster = 结果['roster']
            if not roster:
                return "花名册还是空的。\n\n我可以从已分类的视频中学习人物特征。\n比如：'学习 /已分类视频/小宝'"
            
            回复 = f"👥 **花名册** ({len(roster)} 人)\n\n"
            for p in roster:
                回复 += f"• {p['name']}: {p['feature_count']} 个特征\n"
            
            return 回复
        
        elif 类型 == 'unknown':
            return 结果.get('message', '我不太明白，试试说"扫描下载文件夹"或"找重复视频"')
        
        return "收到！还需要我做什么？"


# ============ Web API ============
def 创建API应用():
    """创建Flask API应用"""
    try:
        from flask import Flask, jsonify, request, render_template_string
        from flask_cors import CORS
    except ImportError:
        print("✗ 请先安装依赖: pip install flask flask-cors")
        return None
    
    app = Flask(__name__)
    CORS(app)
    
    # 全局AI助手实例
    ai助手 = AI助手()
    
    # ============ API 路由 ============
    
    @app.route('/api/chat', methods=['POST'])
    def chat():
        """AI对话接口"""
        data = request.get_json()
        消息 = data.get('message', '')
        
        if not 消息:
            return jsonify({'error': '消息不能为空'}), 400
        
        结果 = ai助手.处理(消息)
        
        return jsonify({
            'intent': 结果['intent'],
            'response': 结果['response'],
            'params': 结果['params'],
            'result': 结果['result']
        })
    
    @app.route('/api/stats')
    def stats():
        """获取统计"""
        with 数据库() as db:
            return jsonify(db.获取统计())
    
    @app.route('/api/videos')
    def videos():
        """获取视频列表"""
        限制 = request.args.get('limit', 50, type=int)
        with 数据库() as db:
            return jsonify(db.获取视频记录(限制=限制))
    
    @app.route('/api/videos/search')
    def search_videos():
        """搜索视频"""
        条件 = {}
        
        if 'person' in request.args:
            条件['人物'] = request.args.get('person')
        if 'path' in request.args:
            条件['路径包含'] = request.args.get('path')
        if 'limit' in request.args:
            条件['限制'] = request.args.get('limit', type=int)
        
        with 数据库() as db:
            return jsonify(db.搜索视频(条件))
    
    @app.route('/api/persons')
    def persons():
        """获取花名册"""
        with 数据库() as db:
            return jsonify(db.获取花名册统计())
    
    @app.route('/api/duplicates')
    def duplicates():
        """获取重复组"""
        with 数据库() as db:
            return jsonify(db.获取重复组())
    
    @app.route('/api/libraries')
    def libraries():
        """获取视频库"""
        with 数据库() as db:
            libs = db.获取所有库()
        return jsonify([{
            'path': l.路径, 'name': l.名称, 'status': l.状态,
            'video_count': l.视频数, 'total_size': l.总大小,
            'persons': l.人物
        } for l in libs])
    
    @app.route('/api/libraries', methods=['POST'])
    def add_library():
        """添加视频库"""
        data = request.get_json()
        path = data.get('path', '')
        
        p = Path(path)
        if not p.exists():
            return jsonify({'error': '路径不存在'}), 400
        
        视频列表 = [v for v in p.rglob("*") if v.suffix.lower() in 视频后缀]
        总大小 = sum(v.stat().st_size for v in 视频列表)
        
        lib = 视频库(
            路径=str(p.absolute()),
            视频数=len(视频列表),
            总大小=总大小
        )
        
        with 数据库() as db:
            db.保存库(lib)
        
        return jsonify({'success': True, 'library': {'name': lib.名称, 'count': len(视频列表)}})
    
    @app.route('/api/scan', methods=['POST'])
    def scan():
        """扫描视频（异步）"""
        data = request.get_json()
        路径 = data.get('path', '')
        模式 = data.get('mode', 'fast')
        
        if not 路径 or not Path(路径).exists():
            return jsonify({'error': '无效路径'}), 400
        
        # 启动任务管理器
        任务管理 = 任务管理器()
        任务管理.启动()
        
        # 提交异步任务
        task_id = 任务管理.提交任务('scan', {
            'path': 路径,
            'mode': 模式
        })
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '扫描任务已提交，请在任务面板查看进度'
        })
    
    @app.route('/api/dedup', methods=['POST'])
    def dedup():
        """查找重复（异步）"""
        # 启动任务管理器
        任务管理 = 任务管理器()
        任务管理.启动()
        
        # 提交异步任务
        task_id = 任务管理.提交任务('dedup', {})
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '去重任务已提交'
        })
    
    @app.route('/api/roster/learn', methods=['POST'])
    def roster_learn():
        """学习人物特征（异步）"""
        data = request.get_json()
        name = data.get('name', '').strip()
        path = data.get('path', '').strip()
        
        if not name:
            return jsonify({'error': '人物名称不能为空'}), 400
        
        p = Path(path)
        if not p.exists():
            return jsonify({'error': '路径不存在'}), 400
        
        # 启动任务管理器
        任务管理 = 任务管理器()
        任务管理.启动()
        
        # 提交异步任务
        task_id = 任务管理.提交任务('learn', {
            'name': name,
            'path': path
        })
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'开始学习人物 "{name}"'
        })
    
    @app.route('/api/tasks')
    def get_tasks():
        """获取所有任务状态"""
        任务管理 = 任务管理器()
        tasks = 任务管理.获取所有任务()
        return jsonify(tasks)
    
    @app.route('/api/tasks/<task_id>')
    def get_task(task_id):
        """获取单个任务状态"""
        任务管理 = 任务管理器()
        task = 任务管理.获取任务状态(task_id)
        if task:
            return jsonify({'id': task_id, **task})
        return jsonify({'error': '任务不存在'}), 404
    
    @app.route('/api/tasks/current')
    def get_current_task():
        """获取当前正在执行的任务"""
        任务管理 = 任务管理器()
        task = 任务管理.获取当前任务()
        if task:
            return jsonify(task)
        return jsonify({'status': 'idle'})
    
    @app.route('/api/thumbnails/generate', methods=['POST'])
    def generate_thumbnails_api():
        """批量生成缩略图（异步）"""
        # 启动任务管理器
        任务管理 = 任务管理器()
        任务管理.启动()
        
        # 提交异步任务
        task_id = 任务管理.提交任务('thumbnail', {})
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '缩略图生成任务已提交'
        })
    
    @app.route('/api/roster/person/<name>', methods=['DELETE'])
    def roster_delete_person(name):
        """删除人物"""
        from urllib.parse import unquote
        name = unquote(name)
        
        try:
            with 数据库() as db:
                db.删除人物特征(name)
            
            return jsonify({'success': True, 'name': name})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    # ============ 缩略图和视频播放 API ============
    
    @app.route('/api/thumbnail/<path:video_path>')
    def get_thumbnail(video_path):
        """获取视频缩略图"""
        try:
            # URL解码路径
            from urllib.parse import unquote
            video_path = unquote(video_path)
            
            if not Path(video_path).exists():
                return jsonify({'error': '视频不存在'}), 404
            
            生成器 = 缩略图生成器()
            缩略图路径 = 生成器.获取缩略图(video_path)
            
            if 缩略图路径 and Path(缩略图路径).exists():
                from flask import send_file
                return send_file(缩略图路径, mimetype='image/jpeg')
            else:
                # 返回默认占位图
                return jsonify({'error': '缩略图生成失败'}), 500
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/video/<path:video_path>')
    def serve_video(video_path):
        """提供视频文件流（支持断点续传）"""
        from urllib.parse import unquote
        from flask import send_file, request, Response
        import mimetypes
        
        try:
            video_path = unquote(video_path)
            video_file = Path(video_path)
            
            if not video_file.exists():
                return jsonify({'error': '视频不存在'}), 404
            
            # 猜测MIME类型
            mime_type, _ = mimetypes.guess_type(str(video_file))
            if not mime_type:
                mime_type = 'video/mp4'
            
            # 支持Range请求（断点续传）
            range_header = request.headers.get('Range', None)
            
            if range_header:
                # 解析Range头
                byte_start, byte_end = 0, None
                try:
                    byte_start = int(range_header.replace('bytes=', '').split('-')[0])
                    byte_end_str = range_header.replace('bytes=', '').split('-')[1]
                    if byte_end_str:
                        byte_end = int(byte_end_str)
                except:
                    pass
                
                file_size = video_file.stat().st_size
                if byte_end is None:
                    byte_end = file_size - 1
                
                length = byte_end - byte_start + 1
                
                def generate():
                    with open(video_file, 'rb') as f:
                        f.seek(byte_start)
                        remaining = length
                        while remaining > 0:
                            chunk_size = min(8192, remaining)
                            data = f.read(chunk_size)
                            if not data:
                                break
                            remaining -= len(data)
                            yield data
                
                rv = Response(generate(), 206, mimetype=mime_type, 
                             direct_passthrough=True)
                rv.headers.add('Content-Range', f'bytes {byte_start}-{byte_end}/{file_size}')
                rv.headers.add('Accept-Ranges', 'bytes')
                rv.headers.add('Content-Length', str(length))
                return rv
            else:
                return send_file(video_file, mimetype=mimetype)
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/video/<path:video_path>/keyframes')
    def get_keyframes(video_path):
        """获取视频关键帧（人物出现时间点）"""
        from urllib.parse import unquote
        
        try:
            video_path = unquote(video_path)
            
            if not Path(video_path).exists():
                return jsonify({'error': '视频不存在'}), 404
            
            # 从数据库获取人物出现时间点
            with 数据库() as db:
                cursor = db.conn.cursor()
                cursor.execute('''
                    SELECT person_name, timestamps FROM person_appearances 
                    WHERE video_path = ?
                ''', (video_path,))
                
                人物出现 = []
                for row in cursor.fetchall():
                    时间点列表 = json.loads(row['timestamps']) if row['timestamps'] else []
                    人物出现.append({
                        'person': row['person_name'],
                        'timestamps': 时间点列表
                    })
                    
                    # 获取关键帧图片
                    if 时间点列表:
                        生成器 = 缩略图生成器()
                        关键帧 = 生成器.获取视频关键帧(video_path, 时间点列表[:5])  # 最多5帧
            
            return jsonify({
                'video_path': video_path,
                'persons': 人物出现,
                'keyframes': 关键帧 if '关键帧' in locals() else []
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/thumbnails/generate', methods=['POST'])
    def generate_thumbnails():
        """批量生成缩略图"""
        try:
            data = request.get_json()
            video_paths = data.get('paths', [])
            
            if not video_paths:
                return jsonify({'error': '没有提供视频路径'}), 400
            
            生成器 = 缩略图生成器()
            结果 = 生成器.批量生成(video_paths)
            
            return jsonify({
                'success': True,
                'generated': len(结果),
                'total': len(video_paths)
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    # ============ Web 界面 ============
    
    HTML_TEMPLATE = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>视频管家 v4.0 - AI-Native</title>
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
            .header h1 { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .header p { color: #666; font-size: 1.1em; }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            .stat-card {
                background: rgba(255,255,255,0.95);
                border-radius: 10px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                transition: transform 0.3s;
            }
            .stat-card:hover {
                transform: translateY(-5px);
            }
            .stat-card h3 { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 2em; 
                margin-bottom: 5px; 
            }
            .stat-card p { color: #666; }
            .section {
                background: rgba(255,255,255,0.95);
                border-radius: 15px;
                padding: 25px;
                margin-bottom: 20px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }
            .section h2 { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 20px; 
                border-bottom: 2px solid #eee; 
                padding-bottom: 10px; 
            }
            .chat-container {
                background: #f8f9fa;
                border-radius: 15px;
                padding: 20px;
                max-height: 500px;
                overflow-y: auto;
                margin-bottom: 15px;
            }
            .chat-message {
                margin-bottom: 15px;
                padding: 12px 16px;
                border-radius: 12px;
                max-width: 80%;
            }
            .chat-user {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                margin-left: auto;
                text-align: right;
            }
            .chat-assistant {
                background: white;
                border: 1px solid #e0e0e0;
                margin-right: auto;
            }
            .chat-input-area {
                display: flex;
                gap: 10px;
            }
            .chat-input {
                flex: 1;
                padding: 12px 16px;
                border: 2px solid #ddd;
                border-radius: 25px;
                font-size: 1em;
                outline: none;
            }
            .chat-input:focus {
                border-color: #667eea;
            }
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 25px;
                cursor: pointer;
                font-size: 1em;
                transition: all 0.3s;
            }
            .btn:hover { 
                transform: translateY(-2px); 
                box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
            }
            .quick-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 15px;
            }
            .quick-btn {
                background: #f0f0f0;
                color: #667eea;
                border: 1px solid #ddd;
                padding: 8px 16px;
                border-radius: 20px;
                cursor: pointer;
                font-size: 0.9em;
                transition: all 0.3s;
            }
            .quick-btn:hover {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-color: transparent;
            }
            .video-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 15px;
            }
            .video-card {
                background: #f8f9fa;
                border-radius: 10px;
                overflow: hidden;
                transition: transform 0.3s;
                cursor: pointer;
            }
            .video-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            .video-thumb {
                width: 100%;
                height: 120px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 2em;
                overflow: hidden;
                position: relative;
            }
            .video-thumb img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .video-thumb .play-icon {
                position: absolute;
                font-size: 1.5em;
                opacity: 0.8;
                text-shadow: 0 2px 10px rgba(0,0,0,0.3);
            }
            .video-info {
                padding: 12px;
            }
            .video-info h4 {
                font-size: 0.95em;
                margin-bottom: 5px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .video-info p {
                font-size: 0.8em;
                color: #666;
            }
            /* 视频播放器模态框 */
            .video-modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.9);
                z-index: 1000;
                justify-content: center;
                align-items: center;
            }
            .video-modal.active {
                display: flex;
            }
            .video-player-container {
                width: 90%;
                max-width: 1200px;
                background: #1a1a1a;
                border-radius: 15px;
                overflow: hidden;
            }
            .video-player-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px 20px;
                background: #2a2a2a;
                color: white;
            }
            .video-player-header h3 {
                margin: 0;
                font-size: 1.1em;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 80%;
            }
            .video-player-header .close-btn {
                background: none;
                border: none;
                color: white;
                font-size: 1.5em;
                cursor: pointer;
            }
            .video-wrapper {
                position: relative;
                padding-bottom: 56.25%; /* 16:9 */
                height: 0;
                background: #000;
            }
            .video-wrapper video {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
            }
            .video-sidebar {
                display: flex;
                gap: 15px;
                padding: 15px;
                background: #2a2a2a;
                max-height: 200px;
                overflow-x: auto;
            }
            .keyframe-item {
                flex-shrink: 0;
                width: 120px;
                text-align: center;
                cursor: pointer;
                transition: transform 0.2s;
            }
            .keyframe-item:hover {
                transform: scale(1.05);
            }
            .keyframe-item img {
                width: 100%;
                height: 68px;
                object-fit: cover;
                border-radius: 8px;
                margin-bottom: 5px;
            }
            .keyframe-item .time {
                color: #aaa;
                font-size: 0.8em;
            }
            .keyframe-item .person {
                color: #667eea;
                font-size: 0.75em;
                margin-top: 2px;
            }
            .person-chips {
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                margin-top: 15px;
            }
            .person-chip {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 10px 18px;
                border-radius: 20px;
                font-size: 0.9em;
                cursor: pointer;
                transition: all 0.3s;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .person-chip:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            }
            .person-chip .avatar {
                width: 24px;
                height: 24px;
                border-radius: 50%;
                background: rgba(255,255,255,0.3);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.8em;
            }
            .person-list {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 15px;
                margin-top: 15px;
            }
            .person-card {
                background: #f8f9fa;
                border-radius: 12px;
                padding: 15px;
                display: flex;
                align-items: center;
                gap: 15px;
                transition: all 0.3s;
                cursor: pointer;
                border: 2px solid transparent;
            }
            .person-card:hover {
                background: #fff;
                border-color: #667eea;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                transform: translateY(-2px);
            }
            .person-card .avatar {
                width: 50px;
                height: 50px;
                border-radius: 50%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 1.3em;
                flex-shrink: 0;
            }
            .person-card .info {
                flex: 1;
            }
            .person-card .info h4 {
                margin: 0 0 5px 0;
                color: #333;
                font-size: 1em;
            }
            .person-card .info p {
                margin: 0;
                color: #888;
                font-size: 0.8em;
            }
            .person-card .actions {
                display: flex;
                gap: 5px;
            }
            .icon-btn {
                background: none;
                border: none;
                color: #667eea;
                cursor: pointer;
                padding: 8px;
                border-radius: 8px;
                transition: all 0.3s;
                font-size: 1.1em;
            }
            .icon-btn:hover {
                background: rgba(102, 126, 234, 0.1);
            }
            .learn-section {
                background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
            }
            .learn-section h3 {
                margin-bottom: 15px;
                color: #333;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .input-row {
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
            }
            .input-row input {
                flex: 1;
                padding: 12px 15px;
                border: 2px solid #ddd;
                border-radius: 8px;
                font-size: 1em;
                transition: border-color 0.3s;
            }
            .input-row input:focus {
                outline: none;
                border-color: #667eea;
            }
            .progress-bar {
                width: 100%;
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
                overflow: hidden;
                margin-top: 10px;
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                transition: width 0.3s;
            }
            /* 任务面板样式 */
            .task-list {
                display: flex;
                flex-direction: column;
                gap: 12px;
                margin-top: 15px;
            }
            .task-item {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 15px;
                display: flex;
                align-items: center;
                gap: 15px;
                transition: all 0.3s;
            }
            .task-item:hover {
                background: #fff;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .task-item.running {
                border-left: 4px solid #667eea;
            }
            .task-item.completed {
                border-left: 4px solid #28a745;
            }
            .task-item.failed {
                border-left: 4px solid #dc3545;
            }
            .task-item.pending {
                border-left: 4px solid #ffc107;
            }
            .task-icon {
                font-size: 1.5em;
                width: 40px;
                text-align: center;
            }
            .task-info {
                flex: 1;
            }
            .task-info h4 {
                margin: 0 0 5px 0;
                font-size: 0.95em;
                color: #333;
            }
            .task-info p {
                margin: 0;
                font-size: 0.8em;
                color: #888;
            }
            .task-progress {
                width: 150px;
            }
            .task-status {
                font-size: 0.75em;
                padding: 4px 10px;
                border-radius: 12px;
                text-transform: uppercase;
            }
            .task-status.running {
                background: rgba(102, 126, 234, 0.1);
                color: #667eea;
            }
            .task-status.completed {
                background: rgba(40, 167, 69, 0.1);
                color: #28a745;
            }
            .task-status.failed {
                background: rgba(220, 53, 69, 0.1);
                color: #dc3545;
            }
            .task-status.pending {
                background: rgba(255, 193, 7, 0.1);
                color: #856404;
            }
            .nav {
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
            }
            .nav-item {
                color: white;
                text-decoration: none;
                padding: 8px 16px;
                border-radius: 20px;
                opacity: 0.8;
                transition: all 0.3s;
            }
            .nav-item:hover, .nav-item.active {
                opacity: 1;
                background: rgba(255,255,255,0.2);
            }
            .empty { text-align: center; color: #999; padding: 40px; }
            .loading {
                display: none;
                text-align: center;
                padding: 20px;
                color: #667eea;
            }
            .loading.show { display: block; }
        </style>
    </head>
    <body>
        <div class="container">
            <nav class="nav">
                <a href="#" class="nav-item active" onclick="showTab('home')">🏠 首页</a>
                <a href="#" class="nav-item" onclick="showTab('videos')">📁 视频库</a>
                <a href="#" class="nav-item" onclick="showTab('persons')">👤 人物</a>
                <a href="#" class="nav-item" onclick="showTab('duplicates')">⚠️ 重复</a>
                <a href="#" class="nav-item" onclick="showTab('tasks')">📋 任务</a>
            </nav>
            
            <div id="tab-home">
                <div class="header">
                    <h1>🎬 视频管家 v4.0</h1>
                    <p>AI-Native 架构 - 像和助理聊天一样管理视频</p>
                </div>
                
                <div class="stats" id="stats">
                    <div class="stat-card">
                        <h3 id="stat-videos">-</h3>
                        <p>📹 视频</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="stat-persons">-</h3>
                        <p>👤 人物</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="stat-duplicates">-</h3>
                        <p>⚠️ 重复</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="stat-size">-</h3>
                        <p>💾 大小</p>
                    </div>
                </div>
                
                <div class="section">
                    <h2>💬 AI 助手</h2>
                    <div class="chat-container" id="chat-container">
                        <div class="chat-message chat-assistant">
                            你好！我是你的视频管家 🤖<br><br>
                            试试这样说：<br>
                            • "扫描下载文件夹"<br>
                            • "找重复视频"<br>
                            • "找包含小宝的视频"
                        </div>
                    </div>
                    <div class="loading" id="loading">正在思考...</div>
                    <div class="chat-input-area">
                        <input type="text" class="chat-input" id="chat-input" 
                               placeholder="输入自然语言指令..." 
                               onkeypress="if(event.key==='Enter')sendMessage()">
                        <button class="btn" onclick="sendMessage()">发送</button>
                    </div>
                    <div class="quick-actions">
                        <button class="quick-btn" onclick="quickChat('扫描下载文件夹')">📂 扫描</button>
                        <button class="quick-btn" onclick="quickChat('找重复视频')">🔍 去重</button>
                        <button class="quick-btn" onclick="quickChat('查看统计')">📊 统计</button>
                        <button class="quick-btn" onclick="quickChat('查看花名册')">👥 人物</button>
                    </div>
                </div>
            </div>
            
            <div id="tab-videos" style="display:none;">
                <div class="section">
                    <h2>📁 视频库</h2>
                    <div id="videos-list" class="video-grid">
                        <div class="empty">加载中...</div>
                    </div>
                </div>
            </div>
            
            <div id="tab-persons" style="display:none;">
                <div class="section">
                    <h2>👤 花名册管理</h2>
                    
                    <!-- 学习功能区 -->
                    <div class="learn-section">
                        <h3>📚 学习新人物</h3>
                        <div class="input-row">
                            <input type="text" id="learn-name" placeholder="人物名称（如：小宝）">
                            <input type="text" id="learn-path" placeholder="视频文件夹路径">
                            <button class="btn" onclick="startLearning()">开始学习</button>
                        </div>
                        <div id="learn-progress" style="display:none;">
                            <p id="learn-status">正在学习...</p>
                            <div class="progress-bar">
                                <div class="progress-fill" id="learn-progress-bar" style="width:0%"></div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 人物列表 -->
                    <h3 style="margin-bottom:15px;">已学习人物</h3>
                    <div id="persons-list" class="person-list">
                        <div class="empty">加载中...</div>
                    </div>
                </div>
            </div>
            
            <div id="tab-duplicates" style="display:none;">
                <div class="section">
                    <h2>⚠️ 重复视频</h2>
                    <div id="duplicates-list">
                        <div class="empty">加载中...</div>
                    </div>
                </div>
            </div>
            
            <div id="tab-tasks" style="display:none;">
                <div class="section">
                    <h2>📋 任务队列</h2>
                    <div id="current-task" style="margin-bottom:20px;"></div>
                    <div id="tasks-list" class="task-list">
                        <div class="empty">暂无任务</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 视频播放器模态框 -->
        <div class="video-modal" id="video-modal">
            <div class="video-player-container">
                <div class="video-player-header">
                    <h3 id="video-title">视频标题</h3>
                    <button class="close-btn" onclick="closeVideoPlayer()">×</button>
                </div>
                <div class="video-wrapper">
                    <video id="video-player" controls preload="metadata">
                        <source src="" type="video/mp4">
                        您的浏览器不支持视频播放
                    </video>
                </div>
                <div class="video-sidebar" id="keyframes-list">
                    <!-- 关键帧列表 -->
                </div>
            </div>
        </div>
        
        <script>
            let currentTab = 'home';
            let currentVideoPath = '';
            
            function showTab(tab) {
                document.querySelectorAll('[id^="tab-"]').forEach(el => el.style.display = 'none');
                document.getElementById('tab-' + tab).style.display = 'block';
                document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
                event.target.classList.add('active');
                currentTab = tab;
                
                if (tab === 'videos') loadVideos();
                if (tab === 'persons') loadPersons();
                if (tab === 'duplicates') loadDuplicates();
            }
            
            async function loadStats() {
                try {
                    const res = await fetch('/api/stats');
                    const data = await res.json();
                    document.getElementById('stat-videos').textContent = data.videos || 0;
                    document.getElementById('stat-persons').textContent = data.persons || 0;
                    document.getElementById('stat-duplicates').textContent = data.duplicates || 0;
                    document.getElementById('stat-size').textContent = 
                        data.total_size ? (data.total_size / 1024**3).toFixed(1) + 'GB' : '0GB';
                } catch(e) { console.error(e); }
            }
            
            function encodePath(path) {
                return encodeURIComponent(path).replace(/%2F/g, '/');
            }
            
            async function loadVideos() {
                try {
                    const res = await fetch('/api/videos?limit=20');
                    const data = await res.json();
                    const container = document.getElementById('videos-list');
                    
                    if (data.length === 0) {
                        container.innerHTML = '<div class="empty">暂无视频，先去扫描吧</div>';
                        return;
                    }
                    
                    container.innerHTML = data.map(v => {
                        const thumbUrl = `/api/thumbnail/${encodePath(v.path)}`;
                        const persons = v.persons && v.persons.length > 0 
                            ? `<p>👤 ${v.persons.slice(0, 2).map(p => p.name).join(', ')}${v.persons.length > 2 ? ' +' + (v.persons.length - 2) : ''}</p>` 
                            : '';
                        return `
                            <div class="video-card" onclick="openVideoPlayer('${encodePath(v.path)}', '${escapeHtml(v.name)}')">
                                <div class="video-thumb">
                                    <img src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'">
                                    <div class="play-icon" style="display:none">🎬</div>
                                </div>
                                <div class="video-info">
                                    <h4>${escapeHtml(v.name)}</h4>
                                    <p>${formatDuration(v.duration)} | ${formatSize(v.size)}</p>
                                    ${persons}
                                </div>
                            </div>
                        `;
                    }).join('');
                } catch(e) { 
                    console.error(e);
                    document.getElementById('videos-list').innerHTML = '<div class="empty">加载失败</div>';
                }
            }
            
            async function openVideoPlayer(videoPath, videoName) {
                currentVideoPath = decodeURIComponent(videoPath);
                document.getElementById('video-title').textContent = videoName;
                document.getElementById('video-modal').classList.add('active');
                
                // 设置视频源
                const videoPlayer = document.getElementById('video-player');
                videoPlayer.src = `/api/video/${videoPath}`;
                videoPlayer.load();
                
                // 加载关键帧
                loadKeyframes(videoPath);
            }
            
            function closeVideoPlayer() {
                const videoPlayer = document.getElementById('video-player');
                videoPlayer.pause();
                videoPlayer.src = '';
                document.getElementById('video-modal').classList.remove('active');
                currentVideoPath = '';
            }
            
            async function loadKeyframes(videoPath) {
                try {
                    const res = await fetch(`/api/video/${videoPath}/keyframes`);
                    const data = await res.json();
                    const container = document.getElementById('keyframes-list');
                    
                    if (!data.persons || data.persons.length === 0) {
                        container.innerHTML = '<div style="color:#888;padding:10px;">未识别到人物</div>';
                        return;
                    }
                    
                    // 合并所有人物的时间点
                    let allKeyframes = [];
                    data.persons.forEach(p => {
                        p.timestamps.forEach(t => {
                            allKeyframes.push({
                                time: t,
                                person: p.person
                            });
                        });
                    });
                    
                    // 去重并排序
                    allKeyframes = allKeyframes
                        .filter((v, i, a) => a.findIndex(t => Math.abs(t.time - v.time) < 5) === i)
                        .sort((a, b) => a.time - b.time)
                        .slice(0, 10);
                    
                    // 获取关键帧图片
                    if (data.keyframes && data.keyframes.length > 0) {
                        container.innerHTML = data.keyframes.map((kf, i) => {
                            const person = allKeyframes[i] ? allKeyframes[i].person : '';
                            return `
                                <div class="keyframe-item" onclick="seekToTime(${kf.time})">
                                    <img src="${kf.image}" alt="">
                                    <div class="time">${formatDuration(kf.time)}</div>
                                    ${person ? `<div class="person">${person}</div>` : ''}
                                </div>
                            `;
                        }).join('');
                    } else {
                        container.innerHTML = allKeyframes.map(kf => `
                            <div class="keyframe-item" onclick="seekToTime(${kf.time})">
                                <div style="width:100%;height:68px;background:#444;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#888;"
003e⏱️</div>
                                <div class="time">${formatDuration(kf.time)}</div>
                                <div class="person">${kf.person}</div>
                            </div>
                        `).join('');
                    }
                } catch(e) {
                    console.error(e);
                    document.getElementById('keyframes-list').innerHTML = '<div style="color:#888;padding:10px;">加载关键帧失败</div>';
                }
            }
            
            function seekToTime(time) {
                const videoPlayer = document.getElementById('video-player');
                videoPlayer.currentTime = time;
                videoPlayer.play();
            }
            
            // 点击模态框背景关闭
            document.getElementById('video-modal').addEventListener('click', function(e) {
                if (e.target === this) {
                    closeVideoPlayer();
                }
            });
            
            // ESC键关闭播放器
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    closeVideoPlayer();
                }
            });
            
            async function loadPersons() {
                try {
                    const res = await fetch('/api/persons');
                    const data = await res.json();
                    const container = document.getElementById('persons-list');
                    
                    if (data.length === 0) {
                        container.innerHTML = '<div class="empty">花名册为空，请先学习人物</div>';
                        return;
                    }
                    
                    container.innerHTML = data.map(p => `
                        <div class="person-card" onclick="searchPersonVideos('${p.name}')">
                            <div class="avatar">${p.name.charAt(0)}</div>
                            <div class="info">
                                <h4>${p.name}</h4>
                                <p>${p.feature_count} 个特征样本 · ${p.sources.length} 个来源</p>
                            </div>
                            <div class="actions" onclick="event.stopPropagation()">
                                <button class="icon-btn" onclick="searchPersonVideos('${p.name}')" title="查找视频">🔍</button>
                                <button class="icon-btn" onclick="deletePerson('${p.name}')" title="删除">🗑️</button>
                            </div>
                        </div>
                    `).join('');
                } catch(e) {
                    console.error(e);
                    document.getElementById('persons-list').innerHTML = '<div class="empty">加载失败</div>';
                }
            }
            
            async function startLearning() {
                const nameInput = document.getElementById('learn-name');
                const pathInput = document.getElementById('learn-path');
                
                const name = nameInput.value.trim();
                const path = pathInput.value.trim();
                
                if (!name || !path) {
                    alert('请输入人物名称和视频路径');
                    return;
                }
                
                try {
                    const res = await fetch('/api/roster/learn', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name: name, path: path})
                    });
                    
                    const data = await res.json();
                    
                    if (data.success) {
                        alert(`✅ ${data.message}\n任务ID: ${data.task_id}`);
                        // 清空输入
                        nameInput.value = '';
                        pathInput.value = '';
                        // 切换到任务标签
                        showTab('tasks');
                    } else {
                        alert('❌ ' + (data.error || '提交失败'));
                    }
                } catch(e) {
                    alert('❌ 请求失败: ' + e.message);
                }
            }
            
            // ============ 任务面板 ============
            let taskRefreshInterval = null;
            
            async function loadTasks() {
                try {
                    const res = await fetch('/api/tasks');
                    const tasks = await res.json();
                    
                    const currentContainer = document.getElementById('current-task');
                    const listContainer = document.getElementById('tasks-list');
                    
                    if (tasks.length === 0) {
                        listContainer.innerHTML = '<div class="empty">暂无任务</div>';
                        currentContainer.innerHTML = '';
                        return;
                    }
                    
                    // 找到正在运行的任务
                    const currentTask = tasks.find(t => t.status === 'running');
                    
                    if (currentTask) {
                        currentContainer.innerHTML = `
                            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 12px;">
                                <h3 style="margin: 0 0 10px 0;">⚡ 正在执行</h3>
                                <p style="margin: 0 0 10px 0;">${getTaskTypeName(currentTask.id)}</p>
                                <div class="progress-bar" style="background: rgba(255,255,255,0.3);">
                                    <div class="progress-fill" style="width: ${currentTask.progress}%"></div>
                                </div>
                                <p style="margin: 10px 0 0 0; font-size: 0.9em;">${currentTask.progress}% - ${currentTask.result?.processed || 0} / ${currentTask.result?.total || 0}</p>
                            </div>
                        `;
                    } else {
                        currentContainer.innerHTML = '';
                    }
                    
                    // 任务列表
                    listContainer.innerHTML = tasks.slice(0, 20).map(t => {
                        const typeName = getTaskTypeName(t.id);
                        const statusClass = t.status;
                        const statusText = {
                            'pending': '等待中',
                            'running': '执行中',
                            'completed': '已完成',
                            'failed': '失败'
                        }[t.status] || t.status;
                        
                        return `
                            <div class="task-item ${statusClass}">
                                <div class="task-icon">${getTaskIcon(t.id)}</div>
                                <div class="task-info">
                                    <h4>${typeName}</h4>
                                    <p>${new Date(t.created).toLocaleString()}</p>
                                </div>
                                ${t.status === 'running' ? `
                                    <div class="task-progress">
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: ${t.progress || 0}%"></div>
                                        </div>
                                    </div>
                                ` : ''}
                                <div class="task-status ${statusClass}">${statusText}</div>
                            </div>
                        `;
                    }).join('');
                } catch(e) {
                    console.error('加载任务失败:', e);
                }
            }
            
            function getTaskTypeName(taskId) {
                if (taskId.startsWith('scan_')) return '扫描视频';
                if (taskId.startsWith('learn_')) return '学习人物';
                if (taskId.startsWith('dedup_')) return '查找重复';
                if (taskId.startsWith('thumbnail_')) return '生成缩略图';
                return '未知任务';
            }
            
            function getTaskIcon(taskId) {
                if (taskId.startsWith('scan_')) return '📂';
                if (taskId.startsWith('learn_')) return '📚';
                if (taskId.startsWith('dedup_')) return '🔍';
                if (taskId.startsWith('thumbnail_')) return '🖼️';
                return '📋';
            }
            
            // 在任务标签页启动定时刷新
            function showTab(tab) {
                // 停止之前的刷新
                if (taskRefreshInterval) {
                    clearInterval(taskRefreshInterval);
                    taskRefreshInterval = null;
                }
                
                document.querySelectorAll('[id^="tab-"]').forEach(el => el.style.display = 'none');
                document.getElementById('tab-' + tab).style.display = 'block';
                document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
                event.target.classList.add('active');
                currentTab = tab;
                
                if (tab === 'videos') loadVideos();
                if (tab === 'persons') loadPersons();
                if (tab === 'duplicates') loadDuplicates();
                if (tab === 'tasks') {
                    loadTasks();
                    // 每2秒刷新一次
                    taskRefreshInterval = setInterval(loadTasks, 2000);
                }
            }
            
            function searchPersonVideos(name) {
                quickChat(`找包含${name}的视频`);
                showTab('home');
                document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
                document.querySelector('.nav-item:first-child').classList.add('active');
            }
            
            async function deletePerson(name) {
                if (!confirm(`确定要删除 "${name}" 吗？\n这将删除该人物的所有特征数据。`)) {
                    return;
                }
                
                try {
                    const res = await fetch(`/api/roster/person/${encodeURIComponent(name)}`, {
                        method: 'DELETE'
                    });
                    
                    const data = await res.json();
                    
                    if (data.success) {
                        loadPersons();
                        loadStats();
                    } else {
                        alert('删除失败: ' + (data.error || '未知错误'));
                    }
                } catch(e) {
                    alert('删除失败: ' + e.message);
                }
            }
            
            async function loadDuplicates() {
                try {
                    const res = await fetch('/api/duplicates');
                    const data = await res.json();
                    const container = document.getElementById('duplicates-list');
                    
                    if (data.length === 0) {
                        container.innerHTML = '<div class="empty">未发现重复视频</div>';
                        return;
                    }
                    
                    container.innerHTML = data.map(g => `
                        <div style="background:#f8f9fa;padding:15px;border-radius:10px;margin-bottom:10px;">
                            <p><strong>${g.type === 'identical' ? '完全重复' : '相似视频'}</strong> 
                               相似度: ${(g.similarity * 100).toFixed(0)}%</p>
                            ${g.files.map(f => `<p style="font-size:0.9em;color:#666;margin:5px 0;">• ${f.split('/').pop()}</p>`).join('')}
                        </div>
                    `).join('');
                } catch(e) {
                    document.getElementById('duplicates-list').innerHTML = '<div class="empty">加载失败</div>';
                }
            }
            
            function formatDuration(seconds) {
                if (!seconds) return '0:00';
                const m = Math.floor(seconds / 60);
                const s = Math.floor(seconds % 60);
                return `${m}:${s.toString().padStart(2, '0')}`;
            }
            
            function formatSize(bytes) {
                if (!bytes) return '0B';
                const gb = bytes / 1024**3;
                if (gb >= 1) return gb.toFixed(1) + 'GB';
                const mb = bytes / 1024**2;
                return mb.toFixed(1) + 'MB';
            }
            
            function quickChat(msg) {
                document.getElementById('chat-input').value = msg;
                sendMessage();
            }
            
            async function sendMessage() {
                const input = document.getElementById('chat-input');
                const msg = input.value.trim();
                if (!msg) return;
                
                // 添加用户消息
                const container = document.getElementById('chat-container');
                container.innerHTML += `<div class="chat-message chat-user">${escapeHtml(msg)}</div>`;
                input.value = '';
                container.scrollTop = container.scrollHeight;
                
                // 显示加载
                document.getElementById('loading').classList.add('show');
                
                try {
                    const res = await fetch('/api/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({message: msg})
                    });
                    const data = await res.json();
                    
                    // 添加AI回复
                    container.innerHTML += `<div class="chat-message chat-assistant">${data.response.replace(/\\n/g, '<br>')}</div>`;
                    container.scrollTop = container.scrollHeight;
                    
                    // 刷新统计
                    loadStats();
                } catch(e) {
                    container.innerHTML += `<div class="chat-message chat-assistant">抱歉，出错了，请重试</div>`;
                }
                
                document.getElementById('loading').classList.remove('show');
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // 初始化
            loadStats();
                
                document.getElementById('loading').classList.remove('show');
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // 初始化
            loadStats();
        </script>
    </body>
    </html>
    '''
    
    @app.route('/')
    def index():
        return render_template_string(HTML_TEMPLATE)
    
    return app


# ============ 命令行入口 ============
def main():
    parser = argparse.ArgumentParser(description='视频管家 v4.0 - AI-Native 架构')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # Web服务
    web_parser = subparsers.add_parser('web', help='启动Web界面')
    web_parser.add_argument('--port', type=int, default=5000, help='端口号')
    web_parser.add_argument('--host', default='0.0.0.0', help='绑定地址')
    
    # AI对话
    chat_parser = subparsers.add_parser('chat', help='命令行AI对话')
    
    # 传统命令
    scan_parser = subparsers.add_parser('scan', help='扫描视频')
    scan_parser.add_argument('path', help='视频路径')
    scan_parser.add_argument('--mode', choices=['simple', 'fast', 'deep'], default='fast')
    
    dup_parser = subparsers.add_parser('dup', help='查找重复')
    
    args = parser.parse_args()
    
    if args.command == 'web':
        app = 创建API应用()
        if app:
            print(f"\n🌐 视频管家 v4.0 启动成功!")
            print(f"   访问: http://localhost:{args.port}")
            print(f"   按 Ctrl+C 停止\n")
            app.run(host=args.host, port=args.port, debug=False)
    
    elif args.command == 'chat':
        print("🎬 视频管家 v4.0 - AI对话模式")
        print("输入 'help' 查看帮助，'exit' 退出\n")
        
        ai = AI助手()
        
        while True:
            try:
                输入 = input("你: ").strip()
                if 输入.lower() in ['exit', 'quit', '退出']:
                    print("再见！👋")
                    break
                if not 输入:
                    continue
                
                结果 = ai.处理(输入)
                print(f"\n🤖 {结果['response']}\n")
                
            except KeyboardInterrupt:
                print("\n再见！👋")
                break
            except Exception as e:
                print(f"错误: {e}")
    
    elif args.command == 'scan':
        处理器 = 视频处理器(模式=args.mode)
        结果 = 处理器.扫描([args.path], 增量=True)
        print(f"\n扫描完成: {结果}")
    
    elif args.command == 'dup':
        处理器 = 视频处理器(模式='快速')
        重复组 = 处理器.查找重复(模式='全部')
        print(f"\n发现 {len(重复组)} 组重复视频")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
