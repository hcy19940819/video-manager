#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoDedup Smart - 智能视频去重工具（方案C完整版）
支持6种算法融合 + 自主学习 + 主动学习
"""

import os
import sys
import json
import sqlite3
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict
import concurrent.futures

# 可选依赖
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            if desc:
                print(f"{desc}...")
        def __iter__(self):
            for item in self.iterable:
                yield item
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def update(self, n=1):
            pass

# 视频处理
try:
    import cv2
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    HAS_VIDEO = True
except ImportError:
    HAS_VIDEO = False
    print("警告: 未安装 opencv-python, pillow, numpy，将使用基础模式")

# ==================== 配置 ====================
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'}

# ==================== 数据模型 ====================
@dataclass
class MultiHashFingerprint:
    """多算法指纹"""
    path: str
    size: int
    mtime: float
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    
    # 6种算法哈希
    phash: str = ""           # pHash - 抗压缩
    ahash: str = ""           # aHash - 速度快
    dhash: str = ""           # dHash - 对边缘敏感
    whash: str = ""           # wHash - 多尺度
    color_hash: str = ""      # 颜色直方图
    orb_features: List[Dict] = None  # ORB特征点
    
    # 快速哈希（组合用于预筛选）
    quick_hash: str = ""      # 向后兼容
    detail_hashes: List[str] = None  # 向后兼容
    
    file_hash: str = ""       # MD5（完全重复确认）
    created_at: str = ""
    scan_version: int = 2       # 版本标记（多算法版）

@dataclass
class DuplicateGroup:
    """重复组"""
    group_id: int
    videos: List[MultiHashFingerprint]
    similarity_type: str  # identical, similar, different_version, maybe
    reason: str
    confidence: float = 0.0  # 置信度（0-1）

# ==================== 6种哈希算法 ====================
class HashExtractors:
    """6种哈希提取器"""
    
    @staticmethod
    def phash(image: np.ndarray, hash_size: int = 8) -> str:
        """pHash - DCT变换，抗压缩、格式转换"""
        if not HAS_VIDEO:
            return ""
        try:
            img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            img = img.convert('L').resize((32, 32), Image.Resampling.LANCZOS)
            pixels = np.array(img, dtype=np.float32)
            dct = cv2.dct(pixels)
            dct_low = dct[:hash_size, :hash_size]
            avg = (dct_low.sum() - dct_low[0, 0]) / (hash_size * hash_size - 1)
            diff = dct_low > avg
            return ''.join(str(int(b)) for b in diff.flatten())
        except:
            return ""
    
    @staticmethod
    def ahash(image: np.ndarray, hash_size: int = 8) -> str:
        """aHash - 平均哈希，速度最快"""
        if not HAS_VIDEO:
            return ""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (hash_size, hash_size))
            avg = resized.mean()
            diff = resized > avg
            return ''.join(str(int(b)) for b in diff.flatten())
        except:
            return ""
    
    @staticmethod
    def dhash(image: np.ndarray, hash_size: int = 8) -> str:
        """dHash - 差异哈希，对边缘/剪辑敏感"""
        if not HAS_VIDEO:
            return ""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (hash_size + 1, hash_size))
            diff = resized[:, 1:] > resized[:, :-1]
            return ''.join(str(int(b)) for b in diff.flatten())
        except:
            return ""
    
    @staticmethod
    def whash(image: np.ndarray, hash_size: int = 8) -> str:
        """wHash - 小波哈希，多尺度分析"""
        if not HAS_VIDEO:
            return ""
        try:
            from scipy.fftpack import dct
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (hash_size, hash_size))
            coeffs = dct(dct(resized.T, norm='ortho').T, norm='ortho')
            avg = coeffs.mean()
            diff = coeffs > avg
            return ''.join(str(int(b)) for b in diff.flatten())
        except:
            return ""
    
    @staticmethod
    def color_hash(image: np.ndarray) -> str:
        """颜色直方图哈希 - 识别滤镜/调色"""
        if not HAS_VIDEO:
            return ""
        try:
            # 提取HSV颜色直方图
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
            hist = cv2.normalize(hist, None).flatten()
            # 量化成二进制
            avg = hist.mean()
            binary = hist > avg
            return ''.join(str(int(b)) for b in binary)
        except:
            return ""
    
    @staticmethod
    def orb_features(image: np.ndarray, max_features: int = 50) -> List[Dict]:
        """ORB特征点 - 几何不变性（旋转/裁剪）"""
        if not HAS_VIDEO:
            return []
        try:
            orb = cv2.ORB_create(nfeatures=max_features)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            kp, des = orb.detectAndCompute(gray, None)
            if des is None:
                return []
            # 保存特征描述符
            features = []
            for i, (k, d) in enumerate(zip(kp[:max_features], des[:max_features])):
                features.append({
                    'x': float(k.pt[0]),
                    'y': float(k.pt[1]),
                    'descriptor': d.tolist()
                })
            return features
        except:
            return []

# ==================== 自主学习系统 ====================
class AdaptiveLearner:
    """自适应学习器 - 从用户反馈中学习"""
    
    def __init__(self, db_path: str = "learner.db"):
        self.db_path = db_path
        self._init_db()
        self.weights = self._load_weights()
        self.threshold = self._load_threshold()
        self.feedback_count = self._count_feedback()
    
    def _init_db(self):
        """初始化学习数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY,
                    video_a TEXT NOT NULL,
                    video_b TEXT NOT NULL,
                    phash_sim REAL,
                    ahash_sim REAL,
                    dhash_sim REAL,
                    whash_sim REAL,
                    color_sim REAL,
                    orb_sim REAL,
                    user_label INTEGER,  -- 1=相同, 0=不同
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS learned_weights (
                    id INTEGER PRIMARY KEY,
                    phash_w REAL DEFAULT 0.30,
                    ahash_w REAL DEFAULT 0.15,
                    dhash_w REAL DEFAULT 0.20,
                    whash_w REAL DEFAULT 0.15,
                    color_w REAL DEFAULT 0.10,
                    orb_w REAL DEFAULT 0.10,
                    threshold REAL DEFAULT 0.75,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 初始化默认权重
            conn.execute('''
                INSERT OR IGNORE INTO learned_weights (id) VALUES (1)
            ''')
            conn.commit()
    
    def _load_weights(self) -> Dict[str, float]:
        """加载学习到的权重"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute('''
                SELECT phash_w, ahash_w, dhash_w, whash_w, color_w, orb_w 
                FROM learned_weights WHERE id=1
            ''').fetchone()
            if row:
                return {
                    'phash': row[0], 'ahash': row[1], 'dhash': row[2],
                    'whash': row[3], 'color': row[4], 'orb': row[5]
                }
            return {'phash': 0.30, 'ahash': 0.15, 'dhash': 0.20, 'whash': 0.15, 'color': 0.10, 'orb': 0.10}
    
    def _load_threshold(self) -> float:
        """加载判断阈值"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute('SELECT threshold FROM learned_weights WHERE id=1').fetchone()
            return row[0] if row else 0.75
    
    def _count_feedback(self) -> int:
        """统计反馈数量"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute('SELECT COUNT(*) FROM feedback').fetchone()
            return row[0] if row else 0
    
    def add_feedback(self, video_a: str, video_b: str, similarities: Dict[str, float], is_same: bool):
        """添加用户反馈"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO feedback 
                (video_a, video_b, phash_sim, ahash_sim, dhash_sim, whash_sim, color_sim, orb_sim, user_label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                video_a, video_b,
                similarities.get('phash', 0),
                similarities.get('ahash', 0),
                similarities.get('dhash', 0),
                similarities.get('whash', 0),
                similarities.get('color', 0),
                similarities.get('orb', 0),
                1 if is_same else 0
            ))
            conn.commit()
        
        self.feedback_count += 1
        
        # 每5个反馈重新学习一次
        if self.feedback_count % 5 == 0:
            self._retrain()
    
    def _retrain(self):
        """重新训练权重"""
        with sqlite3.connect(self.db_path) as conn:
            # 获取所有反馈
            rows = conn.execute('''
                SELECT phash_sim, ahash_sim, dhash_sim, whash_sim, color_sim, orb_sim, user_label
                FROM feedback
            ''').fetchall()
        
        if len(rows) < 5:
            return  # 数据太少不训练
        
        # 简单启发式学习：看哪种算法对正确判断贡献最大
        same_samples = [r for r in rows if r[6] == 1]  # 用户标记相同的
        diff_samples = [r for r in rows if r[6] == 0]  # 用户标记不同的
        
        if not same_samples or not diff_samples:
            return
        
        # 计算每种算法的区分能力
        algos = ['phash', 'ahash', 'dhash', 'whash', 'color', 'orb']
        new_weights = {}
        
        for i, algo in enumerate(algos):
            same_mean = np.mean([r[i] for r in same_samples])
            diff_mean = np.mean([r[i] for r in diff_samples])
            # 差距越大，权重越高
            separation = abs(same_mean - diff_mean)
            new_weights[algo] = max(0.05, separation)
        
        # 归一化
        total = sum(new_weights.values())
        for algo in new_weights:
            new_weights[algo] /= total
        
        # 保存
        self.weights = new_weights
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE learned_weights SET
                    phash_w=?, ahash_w=?, dhash_w=?, whash_w=?, color_w=?, orb_w=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=1
            ''', tuple(new_weights[a] for a in algos))
            conn.commit()
        
        print(f"\n🧠 系统学习了 {len(rows)} 个例子，更新权重：")
        for algo, w in sorted(new_weights.items(), key=lambda x: -x[1]):
            print(f"   {algo}: {w:.2%}")
    
    def get_uncertain_pairs(self, candidates: List[Tuple], top_n: int = 5) -> List[Tuple]:
        """找出系统不确定的视频对（主动学习）"""
        uncertain = []
        for pair_info in candidates:
            # pair_info 包含相似度信息
            video_a, video_b, similarities = pair_info
            
            # 加权计算
            score = sum(similarities.get(a, 0) * w for a, w in self.weights.items())
            confidence = abs(score - self.threshold)
            
            # 越接近阈值越不确定
            if confidence < 0.15:
                uncertain.append((video_a, video_b, score, confidence))
        
        # 按不确定程度排序
        uncertain.sort(key=lambda x: x[3])
        return uncertain[:top_n]
    
    def predict(self, similarities: Dict[str, float]) -> Tuple[bool, float]:
        """预测两个视频是否相同"""
        score = sum(similarities.get(a, 0) * w for a, w in self.weights.items())
        is_same = score >= self.threshold
        return is_same, score

# ==================== 智能视频处理器 ====================
class SmartVideoProcessor:
    """使用6种算法的视频处理器"""
    
    def __init__(self, learner: AdaptiveLearner = None):
        self.learner = learner or AdaptiveLearner()
        self.extractors = HashExtractors()
    
    def process_video(self, video_path: str) -> MultiHashFingerprint:
        """处理单个视频，提取6种指纹"""
        path = Path(video_path)
        stat = path.stat()
        
        fp = MultiHashFingerprint(
            path=str(path.absolute()),
            size=stat.st_size,
            mtime=stat.st_mtime,
            created_at=datetime.now().isoformat()
        )
        
        if not HAS_VIDEO:
            return fp
        
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return fp
        
        # 基本信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0
        
        fp.fps = fps
        fp.width = width
        fp.height = height
        fp.duration = duration
        
        # 采样帧
        frames = self._sample_frames(cap, duration)
        cap.release()
        
        if not frames:
            return fp
        
        # 提取6种哈希
        phashes, ahashes, dhashes, whashes, color_hashes = [], [], [], [], []
        orb_features_list = []
        
        for frame in frames:
            phashes.append(self.extractors.phash(frame))
            ahashes.append(self.extractors.ahash(frame))
            dhashes.append(self.extractors.dhash(frame))
            whashes.append(self.extractors.whash(frame))
            color_hashes.append(self.extractors.color_hash(frame))
            orb_features_list.append(self.extractors.orb_features(frame))
        
        # 取平均/组合
        fp.phash = self._combine_hashes(phashes)
        fp.ahash = self._combine_hashes(ahashes)
        fp.dhash = self._combine_hashes(dhashes)
        fp.whash = self._combine_hashes(whashes)
        fp.color_hash = self._combine_hashes(color_hashes)
        fp.orb_features = orb_features_list[0] if orb_features_list else []
        
        # 向后兼容
        fp.quick_hash = fp.phash
        fp.detail_hashes = phashes
        
        # MD5
        fp.file_hash = self._file_md5(path)
        
        return fp
    
    def _sample_frames(self, cap, duration: float, n_frames: int = 10) -> List[np.ndarray]:
        """均匀采样帧"""
        frames = []
        if duration <= 0:
            return frames
        
        for i in range(n_frames):
            pos = (i + 0.5) / n_frames
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) * pos))
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        
        return frames
    
    def _combine_hashes(self, hashes: List[str]) -> str:
        """组合多个帧的哈希"""
        valid = [h for h in hashes if h]
        if not valid:
            return ""
        # 简单连接
        return valid[len(valid)//2] if valid else ""
    
    def _file_md5(self, path: Path) -> str:
        """计算文件MD5"""
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def calculate_similarities(self, fp1: MultiHashFingerprint, fp2: MultiHashFingerprint) -> Dict[str, float]:
        """计算两个视频在6种算法上的相似度"""
        similarities = {}
        
        # 汉明距离转相似度
        def hash_sim(h1, h2):
            if not h1 or not h2 or len(h1) != len(h2):
                return 0.0
            distance = sum(c1 != c2 for c1, c2 in zip(h1, h2))
            max_dist = len(h1)
            return 1.0 - (distance / max_dist)
        
        similarities['phash'] = hash_sim(fp1.phash, fp2.phash)
        similarities['ahash'] = hash_sim(fp1.ahash, fp2.ahash)
        similarities['dhash'] = hash_sim(fp1.dhash, fp2.dhash)
        similarities['whash'] = hash_sim(fp1.whash, fp2.whash)
        similarities['color'] = hash_sim(fp1.color_hash, fp2.color_hash)
        
        # ORB特征匹配
        similarities['orb'] = self._orb_similarity(fp1.orb_features, fp2.orb_features)
        
        return similarities
    
    def _orb_similarity(self, f1: List[Dict], f2: List[Dict]) -> float:
        """计算ORB特征相似度"""
        if not f1 or not f2:
            return 0.0
        
        # 简化的特征匹配
        matches = 0
        for feat1 in f1[:20]:
            for feat2 in f2[:20]:
                # 欧氏距离
                d1 = np.array(feat1['descriptor'])
                d2 = np.array(feat2['descriptor'])
                dist = np.linalg.norm(d1 - d2)
                if dist < 50:  # 阈值
                    matches += 1
        
        max_matches = min(len(f1), len(f2))
        return min(1.0, matches / max(1, max_matches * 0.3))

# ==================== 智能数据库 ====================
class SmartFingerprintDB:
    """支持多算法的指纹数据库"""
    
    def __init__(self, db_path: str = "videodedup_smart.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    size INTEGER,
                    mtime REAL,
                    duration REAL,
                    width INTEGER,
                    height INTEGER,
                    fps REAL,
                    phash TEXT,
                    ahash TEXT,
                    dhash TEXT,
                    whash TEXT,
                    color_hash TEXT,
                    orb_features TEXT,
                    file_hash TEXT,
                    created_at TEXT,
                    scan_version INTEGER DEFAULT 2
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_phash ON fingerprints(phash)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ahash ON fingerprints(ahash)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_size ON fingerprints(size)')
            conn.commit()
    
    def save(self, fp: MultiHashFingerprint):
        """保存指纹"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO fingerprints
                (path, size, mtime, duration, width, height, fps,
                 phash, ahash, dhash, whash, color_hash, orb_features,
                 file_hash, created_at, scan_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                fp.path, fp.size, fp.mtime, fp.duration, fp.width, fp.height, fp.fps,
                fp.phash, fp.ahash, fp.dhash, fp.whash, fp.color_hash,
                json.dumps(fp.orb_features) if fp.orb_features else '[]',
                fp.file_hash, fp.created_at, fp.scan_version
            ))
            conn.commit()
    
    def get_all(self) -> List[MultiHashFingerprint]:
        """获取所有指纹"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute('SELECT * FROM fingerprints').fetchall()
        
        fps = []
        for row in rows:
            fp = MultiHashFingerprint(
                path=row[1], size=row[2], mtime=row[3], duration=row[4],
                width=row[5], height=row[6], fps=row[7],
                phash=row[8], ahash=row[9], dhash=row[10], whash=row[11],
                color_hash=row[12], orb_features=json.loads(row[13]) if row[13] else [],
                file_hash=row[14], created_at=row[15], scan_version=row[16]
            )
            fps.append(fp)
        return fps

# ==================== 智能去重主类 ====================
class SmartVideoDedup:
    """智能视频去重（6算法+自主学习）"""
    
    def __init__(self, db_path: str = "videodedup_smart.db", learner_path: str = "learner.db"):
        self.db = SmartFingerprintDB(db_path)
        self.learner = AdaptiveLearner(learner_path)
        self.processor = SmartVideoProcessor(self.learner)
    
    def scan(self, paths: List[str], workers: int = 4):
        """扫描视频"""
        video_files = []
        for p in paths:
            path = Path(p)
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                video_files.append(path)
            elif path.is_dir():
                video_files.extend(path.rglob('*'))
                video_files = [f for f in video_files if f.suffix.lower() in VIDEO_EXTENSIONS]
        
        print(f"找到 {len(video_files)} 个视频文件")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            list(tqdm(
                executor.map(self._process_and_save, video_files),
                total=len(video_files),
                desc="扫描进度"
            ))
        
        print(f"\n扫描完成！已学习 {self.learner.feedback_count} 个例子")
    
    def _process_and_save(self, video_path: Path):
        """处理并保存单个视频"""
        fp = self.processor.process_video(str(video_path))
        self.db.save(fp)
    
    def find_duplicates(self, active_learning: bool = False) -> List[DuplicateGroup]:
        """查找重复，支持主动学习"""
        fps = self.db.get_all()
        print(f"数据库中有 {len(fps)} 个视频")
        
        # 计算所有对的相似度
        candidates = []
        for i, fp1 in enumerate(fps):
            for fp2 in fps[i+1:]:
                similarities = self.processor.calculate_similarities(fp1, fp2)
                is_same, score = self.learner.predict(similarities)
                
                if is_same or score > 0.5:  # 可能是重复
                    candidates.append((fp1, fp2, similarities, score))
        
        # 主动学习：找出不确定的询问用户
        if active_learning and candidates:
            uncertain = self.learner.get_uncertain_pairs([
                (a, b, sim) for a, b, sim, _ in candidates
            ], top_n=5)
            
            if uncertain:
                print(f"\n🤔 系统有 {len(uncertain)} 对视频不确定，请帮忙判断：")
                for i, (a, b, score, conf) in enumerate(uncertain, 1):
                    print(f"\n{i}. {Path(a).name}")
                    print(f"   {Path(b).name}")
                    print(f"   系统觉得相似度: {score:.1%}")
        
        # 分组
        groups = self._group_duplicates(candidates)
        return groups
    
    def _group_duplicates(self, candidates) -> List[DuplicateGroup]:
        """将候选对分组"""
        # 简化的分组逻辑
        groups = []
        used = set()
        
        for fp1, fp2, sims, score in sorted(candidates, key=lambda x: -x[3]):
            if fp1.path in used or fp2.path in used:
                continue
            
            group_videos = [fp1, fp2]
            used.add(fp1.path)
            used.add(fp2.path)
            
            # 找更多相似的
            for fp3 in self.db.get_all():
                if fp3.path not in used:
                    s = self.processor.calculate_similarities(fp1, fp3)
                    same, sc = self.learner.predict(s)
                    if same:
                        group_videos.append(fp3)
                        used.add(fp3.path)
            
            groups.append(DuplicateGroup(
                group_id=len(groups)+1,
                videos=group_videos,
                similarity_type='similar' if score < 0.9 else 'identical',
                reason='多算法融合判断',
                confidence=score
            ))
        
        return groups
    
    def teach_system(self, video_a: str, video_b: str, is_same: bool):
        """教系统：这两个视频是否相同"""
        # 获取或生成指纹
        fps = self.db.get_all()
        fp1 = next((f for f in fps if f.path == video_a), None)
        fp2 = next((f for f in fps if f.path == video_b), None)
        
        if not fp1:
            fp1 = self.processor.process_video(video_a)
            self.db.save(fp1)
        if not fp2:
            fp2 = self.processor.process_video(video_b)
            self.db.save(fp2)
        
        # 计算相似度
        similarities = self.processor.calculate_similarities(fp1, fp2)
        
        # 添加反馈
        self.learner.add_feedback(video_a, video_b, similarities, is_same)
        
        action = "相同" if is_same else "不同"
        print(f"✅ 已记录：这两个视频是{action}")
        print(f"   系统已学习 {self.learner.feedback_count} 个例子")
        
        if self.learner.feedback_count >= 5:
            print(f"   学习后的权重：")
            for algo, w in sorted(self.learner.weights.items(), key=lambda x: -x[1]):
                bar = "█" * int(w * 20)
                print(f"   {algo:6s}: {bar} {w:.1%}")

# ==================== 命令行入口 ====================
def main():
    parser = argparse.ArgumentParser(description='VideoDedup Smart - 智能视频去重')
    parser.add_argument('--db', default='videodedup_smart.db', help='数据库路径')
    parser.add_argument('--learner', default='learner.db', help='学习数据库路径')
    
    subparsers = parser.add_subparsers(dest='command')
    
    # scan 命令
    scan_parser = subparsers.add_parser('scan', help='扫描视频')
    scan_parser.add_argument('paths', nargs='+', help='视频路径')
    scan_parser.add_argument('--workers', '-w', type=int, default=4, help='线程数')
    
    # find 命令
    find_parser = subparsers.add_parser('find', help='查找重复')
    find_parser.add_argument('--active-learning', action='store_true', help='主动学习模式')
    
    # teach 命令
    teach_parser = subparsers.add_parser('teach', help='教系统识别')
    teach_parser.add_argument('video_a', help='第一个视频')
    teach_parser.add_argument('video_b', help='第二个视频')
    teach_parser.add_argument('--same', action='store_true', help='标记为相同')
    teach_parser.add_argument('--different', action='store_true', help='标记为不同')
    
    # status 命令
    status_parser = subparsers.add_parser('status', help='查看系统状态')
    
    args = parser.parse_args()
    
    dedup = SmartVideoDedup(args.db, args.learner)
    
    if args.command == 'scan':
        dedup.scan(args.paths, args.workers)
    
    elif args.command == 'find':
        groups = dedup.find_duplicates(active_learning=args.active_learning)
        print(f"\n发现 {len(groups)} 组重复视频")
        for g in groups:
            print(f"\n组 {g.group_id}（置信度 {g.confidence:.1%}）：")
            for v in g.videos:
                print(f"  - {Path(v.path).name}")
    
    elif args.command == 'teach':
        if args.same:
            dedup.teach_system(args.video_a, args.video_b, True)
        elif args.different:
            dedup.teach_system(args.video_a, args.video_b, False)
        else:
            print("请指定 --same 或 --different")
    
    elif args.command == 'status':
        print(f"数据库：{dedup.db.db_path}")
        print(f"视频数量：{len(dedup.db.get_all())}")
        print(f"已学习例子：{dedup.learner.feedback_count}")
        print(f"\n当前算法权重：")
        for algo, w in sorted(dedup.learner.weights.items(), key=lambda x: -x[1]):
            bar = "█" * int(w * 20)
            print(f"  {algo:6s}: {bar} {w:.1%}")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
