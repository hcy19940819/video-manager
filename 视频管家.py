#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 视频管家 v3.0 - 终极整合版

整合功能：
- 🔍 多层pHash去重（VideoDedup）
- 👤 花名册人脸识别（VideoFaceManager）
- 🔎 以图搜视频
- 🌐 Web可视化界面
- 💾 统一SQLite数据库

作者：整合自 hcy19940819/GitHub 私有仓库
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
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict
import concurrent.futures
import itertools

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
阈值_快速 = 5     # 汉明距离，严格
阈值_详细 = 10    # 汉明距离，宽松
阈值_相似 = 0.85  # SSIM

# 采样配置
快速采样间隔 = 30  # 秒
详细关键帧最小 = 5
详细关键帧最大 = 20

项目目录 = Path(__file__).parent
数据目录 = 项目目录 / "data"
人脸库目录 = 数据目录 / "faces"
截图目录 = 数据目录 / "screenshots"

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
    
    # 多层哈希
    快速哈希: str = ""           # pHash（均匀采样）
    详细哈希: List[str] = None   # pHash序列（关键帧）
    文件哈希: str = ""           # MD5前1MB
    
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

# ============ 数据库管理（统一） ============
class 数据库:
    """统一数据库管理"""
    
    def __init__(self, db_path=None):
        数据目录.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(db_path or 数据目录 / "video_master.db")
        self.conn.row_factory = sqlite3.Row
        self.初始化()
    
    def 初始化(self):
        cursor = self.conn.cursor()
        
        # 视频指纹表（去重）
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
                detail_hashes TEXT,  -- JSON数组
                file_hash TEXT,
                created TEXT
            )
        ''')
        
        # 人物特征表（花名册）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS person_features (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                feature TEXT,  -- JSON特征向量
                source_video TEXT,
                created TEXT
            )
        ''')
        
        # 人物出现记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS person_appearances (
                id INTEGER PRIMARY KEY,
                video_path TEXT NOT NULL,
                person_name TEXT NOT NULL,
                timestamps TEXT,  -- JSON数组
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
                persons TEXT,  -- JSON数组
                video_count INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                total_duration REAL DEFAULT 0,
                scanned TEXT,
                created TEXT
            )
        ''')
        
        # 索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_quick ON fingerprints(quick_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_size ON fingerprints(size)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_person_name ON person_features(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_appearance_name ON person_appearances(person_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_lib_status ON libraries(status)')
        
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
            时长=r['duration'], 宽度=r['width'], 高度=r['高度'], 帧率=r['fps'],
            快速哈希=r['quick_hash'] or '',
            详细哈希=json.loads(r['detail_hashes']) if r['detail_hashes'] else [],
            文件哈希=r['file_hash'] or '', 创建时间=r['created'] or ''
        ) for r in rows]
    
    def 获取已有路径(self) -> Set[str]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT path FROM fingerprints')
        return {r[0] for r in cursor.fetchall()}
    
    # ============ 人物特征操作（花名册） ============
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
        """获取所有已学习的人物名"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT DISTINCT name FROM person_features')
        return [r[0] for r in cursor.fetchall()]
    
    def 删除人物特征(self, name: str):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM person_features WHERE name = ?', (name,))
        self.conn.commit()
    
    # ============ 人物出现记录 ============
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
    
    def 获取所有人物(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT DISTINCT person_name FROM person_appearances')
        return [{'name': r[0]} for r in cursor.fetchall()]
    
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
            路径=r['path'], 名称=r['name'], 状态=r['status'],
            人物=json.loads(r['persons']) if r['persons'] else [],
            视频数=r['video_count'], 总大小=r['总大小'],
            总时长=r['total_duration'], 扫描时间=r['scanned'] or '',
            创建时间=r['created'] or ''
        ) for r in cursor.fetchall()]
    
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

# ============ pHash 工具 ============
class pHash工具:
    """感知哈希工具"""
    
    @staticmethod
    def 计算phash(图像) -> str:
        """计算pHash（64位）"""
        if 图像 is None:
            return ""
        
        try:
            # 转灰度
            if len(图像.shape) == 3:
                灰度 = cv2.cvtColor(图像, cv2.COLOR_BGR2GRAY)
            else:
                灰度 = 图像
            
            # 缩放
            小图 = cv2.resize(灰度, (32, 32))
            
            # DCT变换
            dct = cv2.dct(np.float32(小图))
            dct_low = dct[:8, :8]
            
            # 计算均值（排除直流分量）
            avg = (dct_low.sum() - dct_low[0,0]) / 63
            
            # 生成哈希
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

# ============ 核心处理器 ============
class 视频处理器:
    """视频处理核心 - 整合去重+人物识别"""
    
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
        """扫描视频 - 生成指纹+识别人物"""
        print(f"\n{'='*60}")
        print(f"🎬 开始扫描 [模式: {self.模式}]")
        print(f"   硬盘保护: 每{硬盘保护}GB休息{休息秒}秒" if 硬盘保护 > 0 else "   硬盘保护: 关闭")
        print(f"   花名册学习: {'开启' if self.启用花名册 else '关闭'}")
        print(f"{'='*60}")
        
        # 收集视频
        所有视频 = []
        for p in 路径列表:
            所有视频.extend(self._收集视频(p))
        
        if not 所有视频:
            print("未找到视频")
            return {'videos': 0, 'fingerprints': 0, 'persons': 0}
        
        print(f"发现 {len(所有视频)} 个视频")
        
        # 增量过滤
        if 增量:
            with 数据库() as db:
                已有 = db.获取已有路径()
            所有视频 = [v for v in 所有视频 if v not in 已有]
            print(f"新增视频: {len(所有视频)} 个")
        
        if not 所有视频:
            return {'videos': 0, 'fingerprints': 0, 'persons': 0}
        
        # 处理
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
                    
                    # 硬盘保护
                    文件大小 = Path(路径).stat().st_size
                    已处理大小 += 文件大小
                    
                    if 硬盘保护 > 0 and 已处理大小 >= 批量大小:
                        self._休息(休息秒)
                        已处理大小 = 0
                        休息次数 += 1
                        
                except Exception as e:
                    print(f"✗ {Path(路径).name}: {e}")
        
        print(f"\n✅ 扫描完成:")
        print(f"   视频: {视频计数} 个")
        print(f"   指纹: {指纹计数} 个")
        print(f"   人物: {人物计数} 个")
        if 休息次数: print(f"   休息: {休息次数} 次")
        
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
        """处理单个视频 - 生成多层指纹+识别人物"""
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
                
                # 计算多层pHash
                fp.快速哈希 = self._计算快速phash(cap)
                fp.详细哈希 = self._计算详细phash(cap, 总帧数)
                fp.文件哈希 = self._计算md5(路径)
                
                # 识别人物（同时支持普通识别和花名册学习）
                if self.人脸检测 and self.模式 != "简单":
                    人物列表 = self._识别人物(cap, 路径, db)
                    人物计数 = len(人物列表)
                
                cap.release()
        
        db.保存指纹(fp)
        return {'fingerprints': 1, 'persons': 人物计数}
    
    def _计算快速phash(self, cap) -> str:
        """计算快速pHash（中间帧）"""
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
        """计算详细pHash序列（关键帧）"""
        if not cap or not cap.isOpened() or 总帧数 <= 0:
            return []
        
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            间隔 = int(fps * 快速采样间隔)
            
            # 计算关键帧数量
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
        """识别人物（支持花名册模式）"""
        if not cap or not cap.isOpened():
            return []
        
        # 采样配置
        if self.模式 == "深度":
            间隔秒 = 3
            最大帧 = 50
        else:
            间隔秒 = 10
            最大帧 = 10
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        帧间隔 = int(fps * 间隔秒)
        总帧数 = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 收集所有人脸特征
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
                    # 花名册模式：匹配已知人物
                    匹配结果 = self._匹配花名册(特征, db)
                    if 匹配结果:
                        名字, 置信度 = 匹配结果
                        人脸数据[名字]['times'].append(时间点)
                        人脸数据[名字]['conf'].append(置信度)
                else:
                    # 普通模式：临时ID
                    face_id = f"face_{hash(tuple(特征[:5])) % 10000}"
                    人脸数据[face_id]['times'].append(时间点)
                    人脸数据[face_id]['conf'].append(float(face.det_score))
                    人脸数据[face_id]['features'].append(特征)
        
        # 生成记录
        记录列表 = []
        for 名字, 数据 in 人脸数据.items():
            if len(数据['times']) >= 2:  # 至少出现2次
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
        """匹配花名册中的人物"""
        花名册 = db.获取人物特征()
        if not 花名册:
            return None
        
        最佳匹配 = None
        最高相似 = 0.0
        
        for pf in 花名册:
            # 余弦相似度
            相似 = self._余弦相似度(特征, pf.特征向量)
            if 相似 > 最高相似 and 相似 > 0.6:
                最高相似 = 相似
                最佳匹配 = pf.名字
        
        return (最佳匹配, 最高相似) if 最佳匹配 else None
    
    def _余弦相似度(self, a, b) -> float:
        """计算余弦相似度"""
        import numpy as np
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    
    def _休息(self, seconds: int):
        """硬盘保护休息"""
        print(f"\n💤 硬盘保护: 休息 {seconds} 秒...")
        for i in range(seconds, 0, -1):
            print(f"   剩余 {i} 秒...", end='\r')
            time.sleep(1)
        print("   继续扫描!         ")
    
    # ============ 去重功能 ============
    def 查找重复(self, 模式: str = "全部") -> List[Dict]:
        """查找重复视频 - 多层pHash"""
        print("\n🔍 查找重复视频...")
        
        with 数据库() as db:
            指纹列表 = db.获取所有指纹()
        
        if not 指纹列表:
            print("视频库为空")
            return []
        
        重复组 = []
        已处理 = set()
        
        # 第1层：文件大小+时长
        by_key = defaultdict(list)
        for fp in 指纹列表:
            if fp.时长 > 0:
                key = (fp.大小, round(fp.时长))
            else:
                key = (fp.大小,)
            by_key[key].append(fp)
        
        # 检查每组
        for key, 组 in by_key.items():
            if len(组) < 2:
                continue
            
            # 第2层：快速pHash
            for i, fp1 in enumerate(组):
                if fp1.路径 in 已处理:
                    continue
                
                当前组 = [fp1]
                
                for fp2 in 组[i+1:]:
                    if fp2.路径 in 已处理:
                        continue
                    
                    相似类型 = ""
                    
                    # 完全重复：MD5相同
                    if fp1.文件哈希 and fp1.文件哈希 == fp2.文件哈希:
                        相似类型 = "identical"
                    # 快速pHash相似
                    elif fp1.快速哈希 and fp2.快速哈希:
                        dist = self.phash工具.汉明距离(fp1.快速哈希, fp2.快速哈希)
                        if dist <= 阈值_快速:
                            相似类型 = "similar"
                        # 详细pHash序列
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

# ============ 花名册管理 ============
class 花名册管理器:
    """人物花名册管理 - 从已分类视频学习"""
    
    def __init__(self):
        self.处理器 = 视频处理器(模式="深度")
    
    def 学习(self, 分类视频路径: str) -> Dict:
        """从已分类视频学习人物特征"""
        print(f"\n📚 学习花名册: {分类视频路径}")
        print("="*60)
        
        根目录 = Path(分类视频路径)
        if not 根目录.exists():
            print(f"✗ 路径不存在: {分类视频路径}")
            return {'learned': 0}
        
        学习计数 = 0
        
        # 遍历每个人物目录
        with 数据库() as db:
            for 人物目录 in 根目录.iterdir():
                if not 人物目录.is_dir():
                    continue
                
                人物名 = 人物目录.name
                print(f"\n👤 学习: {人物名}")
                
                # 收集该人物的所有视频
                视频列表 = []
                for ext in 视频后缀:
                    视频列表.extend(人物目录.rglob(f"*{ext}"))
                
                if not 视频列表:
                    print(f"   未找到视频")
                    continue
                
                print(f"   找到 {len(视频列表)} 个视频")
                
                # 提取特征
                特征列表 = []
                for 视频路径 in 视频列表:
                    特征 = self._提取人物特征(str(视频路径), 人物名)
                    if 特征:
                        特征列表.append(特征)
                
                # 保存平均特征
                if 特征列表:
                    平均特征 = self._平均特征(特征列表)
                    pf = 人物特征(
                        名字=人物名,
                        特征向量=平均特征,
                        来源视频=str(视频列表[0])
                    )
                    db.保存人物特征(pf)
                    学习计数 += 1
                    print(f"   ✓ 已学习 ({len(特征列表)} 个特征)")
        
        print(f"\n✅ 学习完成: {学习计数} 个人物")
        return {'learned': 学习计数}
    
    def _提取人物特征(self, 视频路径: str, 人物名: str) -> Optional[List[float]]:
        """从视频提取人物特征"""
        if not self.处理器.人脸检测:
            return None
        
        try:
            cap = cv2.VideoCapture(视频路径)
            if not cap.isOpened():
                return None
            
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            总帧数 = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            
            # 采样3个位置
            位置列表 = [总帧数 * 0.2, 总帧数 * 0.5, 总帧数 * 0.8]
            所有特征 = []
            
            for 位置 in 位置列表:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 位置)
                ret, frame = cap.read()
                if not ret:
                    continue
                
                faces = self.处理器.人脸检测.get(frame)
                for face in faces:
                    if face.det_score >= 0.8:
                        所有特征.append(face.embedding.tolist())
            
            cap.release()
            
            if 所有特征:
                return self._平均特征(所有特征)
            return None
        except:
            return None
    
    def _平均特征(self, 特征列表: List[List[float]]) -> List[float]:
        """计算平均特征"""
        import numpy as np
        return np.mean(特征列表, axis=0).tolist()
    
    def 列出人物(self):
        """列出花名册中的人物"""
        with 数据库() as db:
            人物列表 = db.获取花名册人物()
        
        if not 人物列表:
            print("花名册为空")
            return
        
        print(f"\n👥 花名册 ({len(人物列表)} 个人物):")
        for i, 名字 in enumerate(人物列表, 1):
            print(f"  {i}. {名字}")
    
    def 识别人物(self, 未分类路径: str) -> Dict:
        """用花名册识别未分类视频"""
        print(f"\n🔍 识别视频: {未分类路径}")
        print("="*60)
        
        # 使用花名册模式扫描
        处理器 = 视频处理器(模式="深度", 启用花名册=True)
        结果 = 处理器.扫描([未分类路径], 增量=False)
        
        print(f"\n✅ 识别完成")
        return 结果
    
    def 清空(self):
        """清空花名册"""
        with 数据库() as db:
            人物列表 = db.获取花名册人物()
            for 名字 in 人物列表:
                db.删除人物特征(名字)
        print("✅ 花名册已清空")

# ============ 以图搜视频 ============
class 图片搜索引擎:
    """以图搜视频引擎"""
    
    def __init__(self):
        self.处理器 = 视频处理器(模式="深度")
    
    def 搜索(self, 图片路径: str, 视频库路径: str = None, 最小置信度: float = 0.6) -> List[Dict]:
        """上传图片搜索包含该人物的视频"""
        print(f"\n🔍 以图搜视频: {Path(图片路径).name}")
        print("="*60)
        
        if not self.处理器.人脸检测:
            print("✗ AI模型未加载")
            return []
        
        # 1. 提取查询图片的人脸特征
        查询特征 = self._提取图片特征(图片路径)
        if not 查询特征:
            print("✗ 未在图片中检测到人脸")
            return []
        
        print(f"✓ 提取到 {len(查询特征)} 个人脸特征")
        
        # 2. 获取视频列表
        if 视频库路径:
            视频列表 = []
            for ext in 视频后缀:
                视频列表.extend(Path(视频库路径).rglob(f"*{ext}"))
        else:
            # 从数据库获取
            with 数据库() as db:
                指纹列表 = db.获取所有指纹()
                视频列表 = [Path(fp.路径) for fp in 指纹列表]
        
        视频列表 = list(set(视频列表))  # 去重
        print(f"📚 视频库共 {len(视频列表)} 个视频")
        print("\n开始匹配...")
        
        # 3. 匹配每个视频
        结果列表 = []
        
        for i, 视频路径 in enumerate(视频列表, 1):
            print(f"  [{i}/{len(视频列表)}] {视频路径.name}...", end=" ")
            
            匹配结果 = self._匹配视频(视频路径, 查询特征, 最小置信度)
            
            if 匹配结果:
                结果列表.append(匹配结果)
                print(f"✓ 匹配 ({匹配结果['confidence']:.1%})")
            else:
                print("✗")
        
        # 4. 排序返回
        结果列表.sort(key=lambda x: x['confidence'], reverse=True)
        
        print(f"\n✅ 搜索完成，找到 {len(结果列表)} 个匹配视频")
        return 结果列表
    
    def _提取图片特征(self, 图片路径: str) -> List[List[float]]:
        """从图片提取人脸特征"""
        try:
            img = cv2.imread(图片路径)
            if img is None:
                return []
            
            faces = self.处理器.人脸检测.get(img)
            return [face.embedding.tolist() for face in faces if face.det_score >= 0.8]
        except Exception as e:
            print(f"提取特征失败: {e}")
            return []
    
    def _匹配视频(self, 视频路径: Path, 查询特征: List[List[float]], 
                   最小置信度: float) -> Optional[Dict]:
        """匹配单个视频"""
        try:
            cap = cv2.VideoCapture(str(视频路径))
            if not cap.isOpened():
                return None
            
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            总帧数 = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            时长 = 总帧数 / fps if fps > 0 else 0
            
            # 采样策略
            间隔秒 = 5 if 时长 < 300 else 10
            帧间隔 = int(fps * 间隔秒)
            
            最佳匹配 = 0
            匹配时间点 = []
            
            for 帧位置 in range(0, 总帧数, 帧间隔):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 帧位置)
                ret, frame = cap.read()
                if not ret:
                    break
                
                时间点 = 帧位置 / fps
                faces = self.处理器.人脸检测.get(frame)
                
                for face in faces:
                    for 查询 in 查询特征:
                        相似 = self._余弦相似度(face.embedding.tolist(), 查询)
                        if 相似 > 最佳匹配:
                            最佳匹配 = 相似
                        if 相似 >= 最小置信度:
                            匹配时间点.append((时间点, 相似))
            
            cap.release()
            
            if 最佳匹配 >= 最小置信度:
                匹配时间点.sort(key=lambda x: x[1], reverse=True)
                return {
                    'video_path': str(视频路径),
                    'video_name': 视频路径.name,
                    'confidence': 最佳匹配,
                    'timestamps': [t[0] for t in 匹配时间点[:5]],
                    'duration': 时长
                }
            return None
        except Exception as e:
            return None
    
    def _余弦相似度(self, a, b) -> float:
        import numpy as np
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# ============ 库管理 ============
class 库管理器:
    """视频库管理"""
    
    def 添加(self, 路径: str) -> bool:
        p = Path(路径)
        if not p.exists():
            print(f"✗ 路径不存在: {路径}")
            return False
        
        视频列表 = [v for v in p.rglob("*") if v.suffix.lower() in 视频后缀]
        总大小 = sum(v.stat().st_size for v in 视频列表)
        
        lib = 视频库(
            路径=str(p.absolute()),
            视频数=len(视频列表),
            总大小=总大小
        )
        
        with 数据库() as db:
            db.保存库(lib)
        
        print(f"✅ 添加库: {lib.名称}")
        print(f"   视频: {lib.视频数} 个")
        print(f"   大小: {总大小 / (1024**3):.2f} GB")
        return True
    
    def 列出(self):
        with 数据库() as db:
            库列表 = db.获取所有库()
        
        if not 库列表:
            print("暂无视频库")
            return
        
        print(f"\n📚 视频库列表 ({len(库列表)} 个)")
        print("-" * 80)
        for lib in 库列表:
            图标 = {"未分类": "📦", "分类中": "⏳", "已分类": "✅"}.get(lib.状态, "📦")
            print(f"{图标} {lib.名称}")
            print(f"   路径: {lib.路径}")
            print(f"   状态: {lib.状态} | 视频: {lib.视频数} | 大小: {lib.总大小 / (1024**3):.2f} GB")
            if lib.人物:
                print(f"   人物: {', '.join(lib.人物)}")
            print()
    
    def 删除(self, 路径: str):
        with 数据库() as db:
            db.删除库(路径)
        print(f"✅ 已删除库: {路径}")

# ============ Web界面 ============
def 启动Web界面(端口: int = 5000):
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
        <title>视频管家 v3.0</title>
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
            .lib-card {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 15px;
                border-left: 4px solid #667eea;
            }
            .lib-card h3 { color: #333; margin-bottom: 10px; }
            .lib-card p { color: #666; margin: 5px 0; }
            .status { 
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
                transition: all 0.3s;
            }
            .btn:hover { 
                transform: translateY(-2px); 
                box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
            }
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
            .feature-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 15px;
                margin-top: 15px;
            }
            .feature-card {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                border-radius: 10px;
                padding: 20px;
                text-align: center;
            }
            .feature-card h3 { color: #667eea; margin-bottom: 10px; }
            .feature-card p { color: #666; font-size: 0.9em; }
            .empty { text-align: center; color: #999; padding: 40px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎬 视频管家 v3.0</h1>
                <p>终极整合版 - 多层去重 + 花名册学习 + 以图搜视频 + 库管理</p>
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
                <div class="stat-card">
                    <h3 id="roster-count">0</h3>
                    <p>花名册人物</p>
                </div>
            </div>

            <div class="section">
                <h2>✨ 核心功能</h2>
                <div class="feature-grid">
                    <div class="feature-card">
                        <h3>🔍 多层去重</h3>
                        <p>pHash + 文件哈希，精准识别重复视频</p>
                    </div>
                    <div class="feature-card">
                        <h3>👤 花名册学习</h3>
                        <p>从已分类视频自动学习人物特征</p>
                    </div>
                    <div class="feature-card">
                        <h3>🔎 以图搜视频</h3>
                        <p>上传图片，搜索包含该人物的视频</p>
                    </div>
                    <div class="feature-card">
                        <h3>🗂️ 库管理</h3>
                        <p>视频库分类状态管理</p>
                    </div>
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
                    document.getElementById("roster-count").textContent = data.roster || 0;
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
            return jsonify({
                'libraries': len(db.获取所有库()),
                'videos': len(db.获取所有指纹()),
                'persons': len(db.获取所有人物()),
                'roster': len(db.获取花名册人物())
            })
    
    @app.route('/api/libraries')
    def libraries():
        with 数据库() as db:
            libs = db.获取所有库()
        return jsonify([{
            'path': l.路径, 'name': l.名称, 'status': l.状态,
            'video_count': l.视频数, 'total_size': l.总大小,
            'persons': l.人物
        } for l in libs])
    
    @app.route('/api/libraries', methods=['POST'])
    def add_library():
        data = request.get_json()
        mgr = 库管理器()
        return jsonify({'success': mgr.添加(data.get('path', ''))})
    
    print(f"\n🌐 Web界面启动成功!")
    print(f"   本地访问: http://localhost:{端口}")
    print(f"   按 Ctrl+C 停止\n")
    
    app.run(host='0.0.0.0', port=端口, debug=False)

# ============ 命令行入口 ============
def main():
    parser = argparse.ArgumentParser(description='视频管家 v3.0 - 终极整合版')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 初始化
    subparsers.add_parser('init', help='初始化系统')
    
    # 扫描
    scan_parser = subparsers.add_parser('scan', help='扫描视频')
    scan_parser.add_argument('path', help='视频路径')
    scan_parser.add_argument('--mode', choices=['simple', 'fast', 'deep'], default='fast')
    scan_parser.add_argument('--incremental', action='store_true', help='增量扫描')
    scan_parser.add_argument('--roster', action='store_true', help='启用花名册识别')
    scan_parser.add_argument('--protect', type=int, default=100, help='硬盘保护GB')
    scan_parser.add_argument('--rest', type=int, default=10, help='休息秒数')
    
    # 去重
    dup_parser = subparsers.add_parser('dup', help='查找重复视频')
    dup_parser.add_argument('--mode', choices=['quick', 'full'], default='full', help='检测模式')
    
    # 花名册
    roster_parser = subparsers.add_parser('roster', help='花名册管理')
    roster_sub = roster_parser.add_subparsers(dest='roster_cmd')
    learn_parser = roster_sub.add_parser('learn', help='学习已分类视频')
    learn_parser.add_argument('path', help='已分类视频目录')
    roster_sub.add_parser('list', help='列出花名册人物')
    identify_parser = roster_sub.add_parser('identify', help='识别未分类视频')
    identify_parser.add_argument('path', help='未分类视频路径')
    roster_sub.add_parser('clear', help='清空花名册')
    
    # 以图搜视频
    search_parser = subparsers.add_parser('search', help='以图搜视频')
    search_parser.add_argument('image', help='查询图片路径')
    search_parser.add_argument('--lib', help='视频库路径（可选）')
    search_parser.add_argument('--threshold', type=float, default=0.6, help='最小置信度')
    
    # 人物
    subparsers.add_parser('persons', help='列出所有人物')
    
    # 库管理
    lib_parser = subparsers.add_parser('lib', help='库管理')
    lib_sub = lib_parser.add_subparsers(dest='lib_cmd')
    lib_sub.add_parser('list', help='列出所有库')
    add_lib_parser = lib_sub.add_parser('add', help='添加库')
    add_lib_parser.add_argument('path', help='库路径')
    rm_lib_parser = lib_sub.add_parser('rm', help='删除库')
    rm_lib_parser.add_argument('path', help='库路径')
    
    # Web界面
    web_parser = subparsers.add_parser('web', help='启动Web界面')
    web_parser.add_argument('--port', type=int, default=5000)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 执行命令
    if args.command == 'init':
        数据目录.mkdir(exist_ok=True)
        人脸库目录.mkdir(exist_ok=True)
        截图目录.mkdir(exist_ok=True)
        with 数据库() as db:
            pass
        print("✅ 系统初始化完成")
    
    elif args.command == 'scan':
        processor = 视频处理器(模式=args.mode, 启用花名册=args.roster)
        result = processor.扫描(
            [args.path], 增量=args.incremental,
            硬盘保护=args.protect, 休息秒=args.rest
        )
        print(f"\n结果: {result}")
    
    elif args.command == 'dup':
        processor = 视频处理器()
        dups = processor.查找重复(模式='全部' if args.mode == 'full' else '快速')
        if dups:
            print(f"\n发现 {len(dups)} 组重复:")
            for i, dup in enumerate(dups, 1):
                类型说明 = {'identical': '完全重复', 'similar': '相似视频', 'maybe': '可能重复'}
                print(f"\n组 {i} [{类型说明.get(dup['type'], '未知')}] ({dup['count']} 个):")
                for f in dup['files'][:5]:
                    print(f"  - {f}")
                if len(dup['files']) > 5:
                    print(f"  ... 还有 {len(dup['files'])-5} 个")
    
    elif args.command == 'roster':
        mgr = 花名册管理器()
        if args.roster_cmd == 'learn':
            mgr.学习(args.path)
        elif args.roster_cmd == 'list':
            mgr.列出人物()
        elif args.roster_cmd == 'identify':
            mgr.识别人物(args.path)
        elif args.roster_cmd == 'clear':
            mgr.清空()
        else:
            roster_parser.print_help()
    
    elif args.command == 'search':
        engine = 图片搜索引擎()
        results = engine.搜索(args.image, args.lib, args.threshold)
        if results:
            print(f"\n🎯 搜索结果 (Top {len(results)}):")
            for i, r in enumerate(results[:10], 1):
                print(f"\n{i}. {r['video_name']}")
                print(f"   置信度: {r['confidence']:.1%}")
                print(f"   时间点: {', '.join([f'{t:.1f}s' for t in r['timestamps'][:3]])}")
                print(f"   路径: {r['video_path']}")
    
    elif args.command == 'persons':
        with 数据库() as db:
            persons = db.获取所有人物()
            roster = db.获取花名册人物()
        
        print(f"\n👥 花名册人物 ({len(roster)} 个):")
        for name in roster:
            print(f"  📌 {name}")
        
        print(f"\n👤 识别到的人物 ({len(persons)} 个):")
        for p in persons:
            print(f"  - {p['name']}")
    
    elif args.command == 'lib':
        mgr = 库管理器()
        if args.lib_cmd == 'list':
            mgr.列出()
        elif args.lib_cmd == 'add':
            mgr.添加(args.path)
        elif args.lib_cmd == 'rm':
            mgr.删除(args.path)
        else:
            lib_parser.print_help()
    
    elif args.command == 'web':
        启动Web界面(args.port)

if __name__ == '__main__':
    main()
