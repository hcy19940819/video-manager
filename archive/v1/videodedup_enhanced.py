#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoDedup Enhanced - 增强版视频去重核心
专门优化"同一视频不同版本"的检测：
- 不同分辨率/码率
- 带水印/无水印
- 轻微裁剪/黑边
- 开头/结尾有差异
"""

import os
import sys
import json
import sqlite3
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set, NamedTuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import concurrent.futures
from enum import Enum

# 可选依赖
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
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

# 视频处理相关
try:
    import cv2
    import numpy as np
    from PIL import Image
    HAS_VIDEO = True
except ImportError:
    HAS_VIDEO = False
    print("警告: 未安装 opencv-python, pillow, numpy，将使用基础模式")


# ==================== 配置常量 ====================

VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
    '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'
}

class SimilarityMode(Enum):
    """相似度模式"""
    STRICT = "strict"      # 严格：几乎完全相同
    STANDARD = "standard"  # 标准：允许格式/压缩差异
    LOOSE = "loose"        # 宽松：允许水印/轻微裁剪

# 相似度阈值配置
THRESHOLD_CONFIG = {
    SimilarityMode.STRICT: {
        'phash_distance': 3,
        'sequence_similarity': 0.95,
        'color_similarity': 0.95,
        'edge_similarity': 0.95,
        'duration_tolerance': 2,  # 秒
    },
    SimilarityMode.STANDARD: {
        'phash_distance': 8,
        'sequence_similarity': 0.85,
        'color_similarity': 0.80,
        'edge_similarity': 0.80,
        'duration_tolerance': 10,
    },
    SimilarityMode.LOOSE: {
        'phash_distance': 15,
        'sequence_similarity': 0.70,
        'color_similarity': 0.65,
        'edge_similarity': 0.65,
        'duration_tolerance': 30,
    }
}

# 采样配置
QUICK_SAMPLE_INTERVAL = 30   # 快速模式每30秒采样
DETAIL_KEYFRAME_MIN = 5      # 最少关键帧
DETAIL_KEYFRAME_MAX = 20     # 最多关键帧


# ==================== 数据模型 ====================

@dataclass
class EnhancedFingerprint:
    """增强版视频指纹"""
    path: str
    size: int
    mtime: float
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    
    # 多层哈希
    quick_hash: str = ""           # 快速pHash
    detail_hashes: List[str] = field(default_factory=list)  # 详细pHash序列
    file_hash: str = ""            # 文件MD5（前1MB）
    
    # 增强特征
    color_histograms: List[List[float]] = field(default_factory=list)  # 颜色直方图
    edge_features: List[List[float]] = field(default_factory=list)     # 边缘特征
    orb_features: List[List[int]] = field(default_factory=list)        # ORB特征点（可选）
    aspect_ratio: float = 0.0      # 宽高比
    
    # 分段指纹（用于检测开头/结尾差异）
    segment_hashes: List[str] = field(default_factory=list)  # 分段哈希
    
    # 元数据
    created_at: str = ""
    scan_version: int = 2
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if self.aspect_ratio == 0.0 and self.width > 0 and self.height > 0:
            self.aspect_ratio = self.width / self.height
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EnhancedFingerprint':
        return cls(**data)


@dataclass
class DuplicateGroup:
    """重复视频组"""
    group_id: int
    videos: List[EnhancedFingerprint]
    similarity_type: str  # 'identical', 'similar', 'version', 'maybe'
    reason: str
    confidence: float = 0.0  # 置信度 0-1
    details: Dict = field(default_factory=dict)  # 详细对比信息


# ==================== 增强版数据库 ====================

class EnhancedFingerprintDB:
    """增强版指纹数据库"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表结构"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        # 主表：视频指纹
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                duration REAL DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                fps REAL DEFAULT 0,
                aspect_ratio REAL DEFAULT 0,
                quick_hash TEXT,
                detail_hashes TEXT,
                file_hash TEXT,
                color_histograms TEXT,
                edge_features TEXT,
                orb_features TEXT,
                segment_hashes TEXT,
                created_at TEXT,
                scan_version INTEGER DEFAULT 2
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quick_hash ON fingerprints(quick_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_size ON fingerprints(size)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_aspect ON fingerprints(aspect_ratio)')
        
        # 扫描会话记录
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scan_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_path TEXT NOT NULL,
                scan_time TEXT NOT NULL,
                total_files INTEGER DEFAULT 0,
                new_files INTEGER DEFAULT 0,
                updated_files INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0
            )
        ''')
        
        self.conn.commit()
    
    def get_fingerprint(self, path: str) -> Optional[EnhancedFingerprint]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints WHERE path = ?', (path,))
        row = cursor.fetchone()
        return self._row_to_fingerprint(row) if row else None
    
    def get_all_fingerprints(self) -> List[EnhancedFingerprint]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints')
        return [self._row_to_fingerprint(row) for row in cursor.fetchall()]
    
    def get_fingerprints_by_quick_hash(self, quick_hash: str) -> List[EnhancedFingerprint]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints WHERE quick_hash = ?', (quick_hash,))
        return [self._row_to_fingerprint(row) for row in cursor.fetchall()]
    
    def save_fingerprint(self, fp: EnhancedFingerprint) -> bool:
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO fingerprints 
                (path, size, mtime, duration, width, height, fps, aspect_ratio,
                 quick_hash, detail_hashes, file_hash, color_histograms, 
                 edge_features, orb_features, segment_hashes, created_at, scan_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                fp.path, fp.size, fp.mtime, fp.duration, fp.width, fp.height, fp.fps,
                fp.aspect_ratio, fp.quick_hash, json.dumps(fp.detail_hashes), fp.file_hash,
                json.dumps(fp.color_histograms), json.dumps(fp.edge_features),
                json.dumps(fp.orb_features), json.dumps(fp.segment_hashes),
                fp.created_at, fp.scan_version
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"保存指纹失败 {fp.path}: {e}")
            return False
    
    def save_fingerprints_batch(self, fingerprints: List[EnhancedFingerprint]):
        cursor = self.conn.cursor()
        data = [(
            fp.path, fp.size, fp.mtime, fp.duration, fp.width, fp.height, fp.fps,
            fp.aspect_ratio, fp.quick_hash, json.dumps(fp.detail_hashes), fp.file_hash,
            json.dumps(fp.color_histograms), json.dumps(fp.edge_features),
            json.dumps(fp.orb_features), json.dumps(fp.segment_hashes),
            fp.created_at, fp.scan_version
        ) for fp in fingerprints]
        
        cursor.executemany('''
            INSERT OR REPLACE INTO fingerprints 
            (path, size, mtime, duration, width, height, fps, aspect_ratio,
             quick_hash, detail_hashes, file_hash, color_histograms,
             edge_features, orb_features, segment_hashes, created_at, scan_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        self.conn.commit()
    
    def record_scan_session(self, scan_path: str, total: int, new: int, updated: int, duration: float):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO scan_sessions (scan_path, scan_time, total_files, new_files, updated_files, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (scan_path, datetime.now().isoformat(), total, new, updated, duration))
        self.conn.commit()
    
    def _row_to_fingerprint(self, row: sqlite3.Row) -> EnhancedFingerprint:
        def load_json(field):
            return json.loads(field) if field else []
        
        return EnhancedFingerprint(
            path=row['path'],
            size=row['size'],
            mtime=row['mtime'],
            duration=row['duration'],
            width=row['width'],
            height=row['height'],
            fps=row['fps'],
            quick_hash=row['quick_hash'] or '',
            detail_hashes=load_json(row['detail_hashes']),
            file_hash=row['file_hash'] or '',
            color_histograms=load_json(row['color_histograms']),
            edge_features=load_json(row['edge_features']),
            orb_features=load_json(row['orb_features']),
            segment_hashes=load_json(row['segment_hashes']),
            created_at=row['created_at'] or '',
            scan_version=row['scan_version']
        )
    
    def close(self):
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ==================== 增强版视频处理器 ====================

class EnhancedVideoProcessor:
    """增强版视频处理器 - 提取更多特征用于检测不同版本"""
    
    def __init__(self, mode: SimilarityMode = SimilarityMode.STANDARD):
        self.mode = mode
        if not HAS_VIDEO:
            raise RuntimeError("需要安装 opencv-python, pillow, numpy")
    
    def get_video_info(self, path: str) -> Dict:
        """获取视频基本信息"""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return {}
        
        info = {
            'duration': 0.0,
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'total_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        }
        
        if info['fps'] > 0:
            info['duration'] = info['total_frames'] / info['fps']
        
        cap.release()
        return info
    
    def extract_enhanced_fingerprint(self, path: str) -> Optional[EnhancedFingerprint]:
        """提取增强版指纹"""
        try:
            stat = os.stat(path)
            fp = EnhancedFingerprint(
                path=path,
                size=stat.st_size,
                mtime=stat.st_mtime
            )
            
            # 基本信息
            info = self.get_video_info(path)
            if not info:
                return None
            
            fp.duration = info['duration']
            fp.width = info['width']
            fp.height = info['height']
            fp.fps = info['fps']
            fp.aspect_ratio = fp.width / fp.height if fp.height > 0 else 0
            
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                return None
            
            # 1. 快速pHash（均匀采样）
            fp.quick_hash = self._extract_quick_hash(cap, fp.duration)
            
            # 2. 详细pHash序列（关键帧）
            fp.detail_hashes, fp.color_histograms, fp.edge_features = \
                self._extract_keyframe_features(cap, fp.duration)
            
            # 3. 分段哈希（检测开头/结尾差异）
            fp.segment_hashes = self._extract_segment_hashes(cap, fp.duration)
            
            # 4. ORB特征（可选，更robust但较慢）
            if self.mode == SimilarityMode.LOOSE:
                fp.orb_features = self._extract_orb_features(cap, fp.duration)
            
            cap.release()
            
            # 5. 文件哈希
            fp.file_hash = self._compute_file_hash(path)
            
            return fp
            
        except Exception as e:
            print(f"处理失败 {path}: {e}")
            return None
    
    def _extract_quick_hash(self, cap, duration: float) -> str:
        """提取快速pHash"""
        sample_times = self._get_sample_times(duration, max_samples=10)
        hashes = []
        
        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            if ret:
                phash = self._phash_frame(frame)
                if phash:
                    hashes.append(phash)
        
        return self._combine_hashes(hashes) if hashes else ""
    
    def _extract_keyframe_features(self, cap, duration: float) -> Tuple[List[str], List[List[float]], List[List[float]]]:
        """提取关键帧的多维特征"""
        num_frames = max(DETAIL_KEYFRAME_MIN, min(DETAIL_KEYFRAME_MAX, int(duration / 10)))
        interval = duration / num_frames if duration > 0 else 1
        
        phashes = []
        colors = []
        edges = []
        
        for i in range(num_frames):
            t = i * interval + interval / 2
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            
            if ret:
                # pHash
                phash = self._phash_frame(frame)
                if phash:
                    phashes.append(phash)
                
                # 颜色直方图（对压缩/格式变化鲁棒）
                color_hist = self._color_histogram(frame)
                if color_hist:
                    colors.append(color_hist)
                
                # 边缘特征（对裁剪/黑边检测有用）
                edge_feat = self._edge_features(frame)
                if edge_feat:
                    edges.append(edge_feat)
        
        return phashes, colors, edges
    
    def _extract_segment_hashes(self, cap, duration: float) -> List[str]:
        """提取分段哈希（开头、中间、结尾各一段）"""
        if duration < 30:
            return []
        
        segments = []
        segment_times = [
            (5, 15),              # 开头
            (duration/2 - 5, duration/2 + 5),  # 中间
            (duration - 15, duration - 5)      # 结尾
        ]
        
        for start, end in segment_times:
            segment_hashes = []
            t = start
            while t < end:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ret, frame = cap.read()
                if ret:
                    phash = self._phash_frame(frame)
                    if phash:
                        segment_hashes.append(phash)
                t += 2  # 每2秒采样
            
            if segment_hashes:
                segments.append(self._combine_hashes(segment_hashes))
        
        return segments
    
    def _extract_orb_features(self, cap, duration: float, max_features: int = 100) -> List[List[int]]:
        """提取ORB特征点（对旋转/缩放鲁棒）"""
        orb = cv2.ORB_create(nfeatures=50)
        features = []
        
        sample_times = self._get_sample_times(duration, max_samples=5)
        
        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                kp, des = orb.detectAndCompute(gray, None)
                if des is not None:
                    # 只保存描述符的简化版本（节省空间）
                    simplified = [int(x) for x in des[0][:16]] if len(des) > 0 else []
                    features.append(simplified)
        
        return features
    
    def _phash_frame(self, frame) -> Optional[str]:
        """计算pHash"""
        try:
            # 1. 缩小尺寸
            resized = cv2.resize(frame, (32, 32), interpolation=cv2.INTER_LANCZOS4)
            # 2. 转灰度
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            # 3. DCT变换
            dct = cv2.dct(np.float32(gray))
            # 4. 取低频
            dct_low = dct[:8, :8]
            # 5. 计算均值并二值化
            avg = (dct_low.sum() - dct_low[0, 0]) / 63
            hash_bits = (dct_low > avg).flatten().astype(int)
            hash_str = ''.join(str(b) for b in hash_bits)
            return hex(int(hash_str, 2))[2:].zfill(16)
        except Exception:
            return None
    
    def _color_histogram(self, frame) -> Optional[List[float]]:
        """提取颜色直方图（HSV空间，对压缩变化鲁棒）"""
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            # 计算H和S通道的直方图
            h_hist = cv2.calcHist([hsv], [0], None, [16], [0, 180])
            s_hist = cv2.calcHist([hsv], [1], None, [8], [0, 256])
            
            # 归一化并合并
            cv2.normalize(h_hist, h_hist)
            cv2.normalize(s_hist, s_hist)
            
            combined = list(h_hist.flatten()) + list(s_hist.flatten())
            return [float(x) for x in combined]
        except Exception:
            return None
    
    def _edge_features(self, frame) -> Optional[List[float]]:
        """提取边缘特征（Canny边缘检测）"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            
            # 将图像分成4x4网格，计算每个网格的边缘密度
            h, w = edges.shape
            cell_h, cell_w = h // 4, w // 4
            features = []
            
            for i in range(4):
                for j in range(4):
                    cell = edges[i*cell_h:(i+1)*cell_h, j*cell_w:(j+1)*cell_w]
                    edge_ratio = np.sum(cell > 0) / (cell_h * cell_w)
                    features.append(float(edge_ratio))
            
            return features
        except Exception:
            return None
    
    def _get_sample_times(self, duration: float, max_samples: int = 10) -> List[float]:
        """获取采样时间点"""
        if duration < 5:
            return [0]
        
        if duration < max_samples * 5:
            return [i * duration / max_samples for i in range(max_samples)]
        
        interval = duration / max_samples
        return [i * interval + interval / 2 for i in range(max_samples)]
    
    def _combine_hashes(self, hashes: List[str]) -> str:
        """合并多个哈希"""
        if not hashes:
            return ""
        if len(hashes) == 1:
            return hashes[0]
        return ''.join(h[:6] for h in hashes[:4]).ljust(16, '0')[:16]
    
    def _compute_file_hash(self, path: str, max_size: int = 1024*1024) -> str:
        """计算文件哈希"""
        try:
            hasher = hashlib.md5()
            with open(path, 'rb') as f:
                data = f.read(max_size)
                hasher.update(data)
            return hasher.hexdigest()
        except Exception:
            return ""


# ==================== 增强版相似度计算 ====================

class EnhancedSimilarityCalculator:
    """增强版相似度计算 - 支持多种特征的加权比对"""
    
    def __init__(self, mode: SimilarityMode = SimilarityMode.STANDARD):
        self.mode = mode
        self.thresholds = THRESHOLD_CONFIG[mode]
    
    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """计算汉明距离"""
        if not hash1 or not hash2 or len(hash1) != len(hash2):
            return float('inf')
        
        try:
            bin1 = bin(int(hash1, 16))[2:].zfill(64)
            bin2 = bin(int(hash2, 16))[2:].zfill(64)
            return sum(c1 != c2 for c1, c2 in zip(bin1, bin2))
        except ValueError:
            return float('inf')
    
    def color_histogram_similarity(self, hist1: List[float], hist2: List[float]) -> float:
        """计算颜色直方图相似度（巴氏距离）"""
        if not hist1 or not hist2 or len(hist1) != len(hist2):
            return 0.0
        
        try:
            # 余弦相似度
            dot = sum(a * b for a, b in zip(hist1, hist2))
            norm1 = sum(a * a for a in hist1) ** 0.5
            norm2 = sum(b * b for b in hist2) ** 0.5
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot / (norm1 * norm2)
        except Exception:
            return 0.0
    
    def edge_feature_similarity(self, feat1: List[float], feat2: List[float]) -> float:
        """计算边缘特征相似度"""
        if not feat1 or not feat2 or len(feat1) != len(feat2):
            return 0.0
        
        # 计算欧氏距离的倒数
        diff = sum((a - b) ** 2 for a, b in zip(feat1, feat2))
        return 1.0 / (1.0 + diff ** 0.5)
    
    def sequence_similarity(self, seq1: List[str], seq2: List[str]) -> float:
        """计算序列相似度（支持不同长度的序列）"""
        if not seq1 or not seq2:
            return 0.0
        
        # 动态规划找最佳匹配
        m, n = len(seq1), len(seq2)
        
        # 简化的匹配：找每个元素的最佳匹配
        matches = 0
        threshold = self.thresholds['phash_distance']
        used = set()
        
        for h1 in seq1:
            best_match = None
            best_dist = float('inf')
            
            for j, h2 in enumerate(seq2):
                if j in used:
                    continue
                dist = self.hamming_distance(h1, h2)
                if dist < best_dist:
                    best_dist = dist
                    best_match = j
            
            if best_match is not None and best_dist <= threshold:
                matches += 1
                used.add(best_match)
        
        return matches / max(m, n)
    
    def segment_similarity(self, seg1: List[str], seg2: List[str]) -> Dict[str, float]:
        """分段相似度分析（检测开头/中间/结尾差异）"""
        if not seg1 or not seg2 or len(seg1) != len(seg2):
            return {'overall': 0.0}
        
        similarities = []
        segment_names = ['beginning', 'middle', 'end']
        result = {}
        
        for i, (s1, s2) in enumerate(zip(seg1, seg2)):
            dist = self.hamming_distance(s1, s2)
            sim = max(0, 1.0 - dist / 20)  # 归一化
            similarities.append(sim)
            if i < len(segment_names):
                result[segment_names[i]] = sim
        
        result['overall'] = sum(similarities) / len(similarities)
        return result
    
    def analyze_differences(self, fp1: EnhancedFingerprint, fp2: EnhancedFingerprint) -> Dict:
        """分析两个视频的具体差异"""
        differences = {
            'resolution': {
                'video1': f"{fp1.width}x{fp1.height}",
                'video2': f"{fp2.width}x{fp2.height}",
                'same_aspect': abs(fp1.aspect_ratio - fp2.aspect_ratio) < 0.1
            },
            'duration_diff': abs(fp1.duration - fp2.duration),
            'size_diff': abs(fp1.size - fp2.size) / (1024**2),  # MB
        }
        
        # 分段对比
        if fp1.segment_hashes and fp2.segment_hashes:
            seg_sim = self.segment_similarity(fp1.segment_hashes, fp2.segment_hashes)
            differences['segment_similarity'] = seg_sim
            
            # 判断是否只是开头/结尾不同
            if seg_sim.get('middle', 0) > 0.9:
                if seg_sim.get('beginning', 0) < 0.5:
                    differences['note'] = "视频主体相同，开头有差异（可能是片头不同）"
                elif seg_sim.get('end', 0) < 0.5:
                    differences['note'] = "视频主体相同，结尾有差异（可能是片尾不同）"
        
        return differences
    
    def are_duplicates(self, fp1: EnhancedFingerprint, fp2: EnhancedFingerprint) -> Tuple[bool, str, float, Dict]:
        """
        判断两个视频是否为重复/同一内容的不同版本
        
        Returns: (is_duplicate, reason, confidence, details)
        """
        details = {}
        
        # 1. 文件完全相同
        if fp1.size == fp2.size and fp1.file_hash and fp2.file_hash:
            if fp1.file_hash == fp2.file_hash:
                return True, "identical_file", 1.0, {}
        
        # 2. 时长差异太大
        duration_diff = abs(fp1.duration - fp2.duration)
        if duration_diff > self.thresholds['duration_tolerance']:
            return False, "", 0.0, {}
        
        # 3. 快速哈希比对
        quick_dist = float('inf')
        if fp1.quick_hash and fp2.quick_hash:
            quick_dist = self.hamming_distance(fp1.quick_hash, fp2.quick_hash)
            
            if quick_dist <= self.thresholds['phash_distance']:
                # 可能是完全相同或不同版本
                if quick_dist <= 3:
                    return True, "identical_content", 0.95, {}
                
                # 详细比对
                if fp1.detail_hashes and fp2.detail_hashes:
                    seq_sim = self.sequence_similarity(fp1.detail_hashes, fp2.detail_hashes)
                    
                    if seq_sim >= self.thresholds['sequence_similarity']:
                        # 检查是否为不同版本
                        if fp1.width != fp2.width or fp1.height != fp2.height:
                            details['resolution_diff'] = f"{fp1.width}x{fp1.height} vs {fp2.width}x{fp2.height}"
                            return True, "different_resolution", seq_sim, details
                        
                        return True, "identical_sequence", seq_sim, details
        
        # 4. 颜色直方图比对（对压缩/格式变化鲁棒）
        color_sim = 0.0
        if fp1.color_histograms and fp2.color_histograms:
            color_sims = []
            for h1, h2 in zip(fp1.color_histograms, fp2.color_histograms):
                sim = self.color_histogram_similarity(h1, h2)
                color_sims.append(sim)
            color_sim = sum(color_sims) / len(color_sims) if color_sims else 0.0
            
            if color_sim >= self.thresholds['color_similarity']:
                # 颜色相似，但pHash不同，可能是水印/裁剪
                details['color_similarity'] = color_sim
        
        # 5. 边缘特征比对（检测裁剪/黑边）
        edge_sim = 0.0
        if fp1.edge_features and fp2.edge_features:
            edge_sims = []
            for e1, e2 in zip(fp1.edge_features, fp2.edge_features):
                sim = self.edge_feature_similarity(e1, e2)
                edge_sims.append(sim)
            edge_sim = sum(edge_sims) / len(edge_sims) if edge_sims else 0.0
            
            if edge_sim >= self.thresholds['edge_similarity']:
                details['edge_similarity'] = edge_sim
        
        # 6. 分段对比（检测片头片尾差异）
        segment_sim = 0.0
        if fp1.segment_hashes and fp2.segment_hashes:
            seg_result = self.segment_similarity(fp1.segment_hashes, fp2.segment_hashes)
            segment_sim = seg_result['overall']
            
            # 如果中间部分很相似，但开头/结尾不同
            if seg_result.get('middle', 0) > 0.9:
                if seg_result.get('beginning', 0) < 0.5 or seg_result.get('end', 0) < 0.5:
                    return True, "same_content_different_editing", 0.8, seg_result
        
        # 7. 综合判断
        confidence = 0.0
        
        if color_sim > 0.9 and edge_sim > 0.9:
            # 颜色和边缘都很相似，可能是不同压缩/水印版本
            confidence = (color_sim + edge_sim) / 2
            if confidence >= self.thresholds['color_similarity']:
                return True, "possible_different_version", confidence, details
        
        if quick_dist <= self.thresholds['phash_distance'] + 5:
            # pHash接近但未达到阈值，可能是轻微裁剪
            confidence = max(0, 1.0 - quick_dist / 20)
            if confidence > 0.6:
                return True, "possible_similar", confidence, details
        
        return False, "", confidence, details


# ==================== 主程序 ====================

class EnhancedVideoDedup:
    """增强版视频去重主类"""
    
    def __init__(self, db_path: str = "videodedup.db", 
                 workers: int = 4,
                 mode: SimilarityMode = SimilarityMode.STANDARD):
        self.db_path = db_path
        self.workers = workers
        self.mode = mode
        self.processor = EnhancedVideoProcessor(mode) if HAS_VIDEO else None
        self.similarity = EnhancedSimilarityCalculator(mode)
        self._scan_stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0}
    
    def scan(self, paths: List[str], incremental: bool = True, 
             update_existing: bool = False) -> List[EnhancedFingerprint]:
        """扫描路径生成指纹"""
        # 收集所有视频文件
        video_files = []
        for path in paths:
            video_files.extend(self._collect_videos(path))
        
        self._scan_stats['total'] = len(video_files)
        
        # 过滤和分类
        with EnhancedFingerprintDB(self.db_path) as db:
            to_process = []
            
            for filepath in video_files:
                existing = db.get_fingerprint(filepath)
                
                if existing is None:
                    to_process.append(filepath)
                    self._scan_stats['new'] += 1
                elif update_existing:
                    mtime = os.path.getmtime(filepath)
                    if mtime > existing.mtime:
                        to_process.append(filepath)
                        self._scan_stats['updated'] += 1
                    else:
                        self._scan_stats['skipped'] += 1
                else:
                    self._scan_stats['skipped'] += 1
        
        if not to_process:
            print("没有新文件需要处理")
            return []
        
        print(f"\n扫描统计: 总视频{self._scan_stats['total']}, "
              f"新文件{self._scan_stats['new']}, "
              f"待更新{self._scan_stats['updated']}, "
              f"跳过{self._scan_stats['skipped']}")
        print(f"\n开始处理 {len(to_process)} 个文件...")
        
        # 并行处理
        fingerprints = []
        start_time = datetime.now()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_path = {executor.submit(self._process_video, path): path 
                             for path in to_process}
            
            for future in tqdm(concurrent.futures.as_completed(future_to_path), 
                              total=len(to_process), desc="生成指纹"):
                try:
                    fp = future.result()
                    if fp:
                        fingerprints.append(fp)
                except Exception as e:
                    print(f"\n处理失败: {e}")
        
        # 批量保存
        if fingerprints:
            with EnhancedFingerprintDB(self.db_path) as db:
                db.save_fingerprints_batch(fingerprints)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        with EnhancedFingerprintDB(self.db_path) as db:
            db.record_scan_session(
                json.dumps(paths), self._scan_stats['total'],
                self._scan_stats['new'], self._scan_stats['updated'], duration
            )
        
        print(f"\n处理完成: {len(fingerprints)} 个指纹已保存, 耗时 {duration:.1f} 秒")
        return fingerprints
    
    def _collect_videos(self, path: str) -> List[str]:
        """收集视频文件"""
        videos = []
        p = Path(path)
        
        if p.is_file():
            if p.suffix.lower() in VIDEO_EXTENSIONS:
                videos.append(str(p.absolute()))
        elif p.is_dir():
            for ext in VIDEO_EXTENSIONS:
                videos.extend(str(f.absolute()) for f in p.rglob(f"*{ext}"))
                videos.extend(str(f.absolute()) for f in p.rglob(f"*{ext.upper()}"))
        
        return videos
    
    def _process_video(self, path: str) -> Optional[EnhancedFingerprint]:
        """处理单个视频"""
        if self.processor:
            return self.processor.extract_enhanced_fingerprint(path)
        return None
    
    def find_duplicates(self, paths: Optional[List[str]] = None,
                       cross_compare: bool = False) -> List[DuplicateGroup]:
        """查找重复视频"""
        with EnhancedFingerprintDB(self.db_path) as db:
            all_fps = db.get_all_fingerprints()
        
        if paths:
            path_set = set(str(Path(p).absolute()) for p in paths)
            all_fps = [fp for fp in all_fps 
                      if any(fp.path.startswith(p) for p in path_set)]
        
        print(f"\n共 {len(all_fps)} 个视频需要对比 [模式: {self.mode.value}]")
        
        # 按宽高比分组（预筛选）
        aspect_groups = defaultdict(list)
        for fp in all_fps:
            # 宽高比相近的归为一组
            aspect_key = round(fp.aspect_ratio * 10) if fp.aspect_ratio > 0 else 0
            aspect_groups[aspect_key].append(fp)
        
        # 查找重复组
        duplicate_groups = []
        processed = set()
        group_id = 0
        
        for aspect_key, fps in tqdm(aspect_groups.items(), desc="对比分组"):
            if len(fps) < 2:
                continue
            
            for i, fp1 in enumerate(fps):
                if fp1.path in processed:
                    continue
                
                group = [fp1]
                group_details = []
                
                for fp2 in fps[i+1:]:
                    if fp2.path in processed:
                        continue
                    
                    is_dup, reason, confidence, details = \
                        self.similarity.are_duplicates(fp1, fp2)
                    
                    if is_dup:
                        group.append(fp2)
                        processed.add(fp2.path)
                        group_details.append({
                            'path': fp2.path,
                            'reason': reason,
                            'confidence': confidence,
                            'details': details
                        })
                
                if len(group) > 1:
                    processed.add(fp1.path)
                    group_id += 1
                    
                    # 确定相似度类型
                    if reason.startswith('identical'):
                        sim_type = 'identical'
                    elif reason.startswith('different_resolution'):
                        sim_type = 'different_version'
                    elif reason.startswith('same_content'):
                        sim_type = 'different_editing'
                    elif reason.startswith('possible'):
                        sim_type = 'maybe'
                    else:
                        sim_type = 'similar'
                    
                    avg_confidence = sum(d['confidence'] for d in group_details) / len(group_details) if group_details else 1.0
                    
                    duplicate_groups.append(DuplicateGroup(
                        group_id=group_id,
                        videos=group,
                        similarity_type=sim_type,
                        reason=reason,
                        confidence=avg_confidence,
                        details={'comparisons': group_details}
                    ))
        
        return duplicate_groups
    
    def compare_with_external(self, external_db_path: str, 
                             current_paths: Optional[List[str]] = None) -> List[DuplicateGroup]:
        """与外部指纹库对比"""
        with EnhancedFingerprintDB(self.db_path) as db:
            current_fps = db.get_all_fingerprints()
        
        if current_paths:
            path_set = set(str(Path(p).absolute()) for p in current_paths)
            current_fps = [fp for fp in current_fps 
                          if any(fp.path.startswith(p) for p in path_set)]
        
        with EnhancedFingerprintDB(external_db_path) as ext_db:
            external_fps = ext_db.get_all_fingerprints()
        
        print(f"\n当前库: {len(current_fps)} 个视频")
        print(f"外部库: {len(external_fps)} 个视频")
        print("\n开始跨库对比...")
        
        duplicate_groups = []
        group_id = 0
        
        for fp1 in tqdm(current_fps, desc="跨库对比"):
            group = [fp1]
            
            for fp2 in external_fps:
                is_dup, reason, confidence, details = \
                    self.similarity.are_duplicates(fp1, fp2)
                
                if is_dup:
                    group.append(fp2)
            
            if len(group) > 1:
                group_id += 1
                sim_type = 'identical' if reason.startswith('identical') else 'similar'
                
                duplicate_groups.append(DuplicateGroup(
                    group_id=group_id,
                    videos=group,
                    similarity_type=sim_type,
                    reason=f"cross_db:{reason}",
                    confidence=confidence
                ))
        
        return duplicate_groups
    
    def export_results(self, groups: List[DuplicateGroup], output_path: str):
        """导出结果"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# VideoDedup 去重报告\n")
            f.write(f"生成时间: {datetime.now().isoformat()}\n")
            f.write(f"相似度模式: {self.mode.value}\n")
            f.write(f"发现重复组: {len(groups)}\n\n")
            
            for group in groups:
                type_names = {
                    'identical': '完全相同',
                    'different_version': '不同版本',
                    'different_editing': '不同剪辑',
                    'similar': '相似视频',
                    'maybe': '可能相关'
                }
                type_name = type_names.get(group.similarity_type, group.similarity_type)
                
                f.write(f"## 重复组 #{group.group_id} [{type_name}]\n")
                f.write(f"原因: {group.reason}\n")
                f.write(f"置信度: {group.confidence:.2%}\n")
                f.write(f"视频数量: {len(group.videos)}\n\n")
                
                if group.details:
                    f.write("详细信息:\n")
                    if 'resolution_diff' in group.details:
                        f.write(f"- 分辨率差异: {group.details['resolution_diff']}\n")
                    if 'segment_similarity' in group.details:
                        seg = group.details['segment_similarity']
                        f.write(f"- 分段相似度: 开头{seg.get('beginning', 0):.2%}, "
                               f"中间{seg.get('middle', 0):.2%}, "
                               f"结尾{seg.get('end', 0):.2%}\n")
                    if 'note' in group.details:
                        f.write(f"- 备注: {group.details['note']}\n")
                    f.write("\n")
                
                # 按质量排序
                sorted_videos = sorted(group.videos, 
                    key=lambda x: (x.width * x.height, x.size), reverse=True)
                
                f.write("| 建议 | 文件路径 | 大小 | 时长 | 分辨率 |\n")
                f.write("|------|----------|------|------|--------|\n")
                
                for i, v in enumerate(sorted_videos):
                    action = "保留" if i == 0 else "可删除"
                    size_mb = v.size / (1024 * 1024)
                    duration_str = f"{v.duration:.1f}s" if v.duration > 0 else "未知"
                    resolution = f"{v.width}x{v.height}" if v.width > 0 else "未知"
                    
                    f.write(f"| {action} | `{v.path}` | {size_mb:.1f}MB | "
                           f"{duration_str} | {resolution} |\n")
                
                f.write("\n---\n\n")
        
        print(f"\n结果已导出: {output_path}")
    
    def stats(self):
        """显示统计"""
        with EnhancedFingerprintDB(self.db_path) as db:
            all_fps = db.get_all_fingerprints()
        
        total_size = sum(fp.size for fp in all_fps)
        total_duration = sum(fp.duration for fp in all_fps)
        
        print(f"\n=== 数据库统计 ===")
        print(f"指纹数量: {len(all_fps)}")
        print(f"总大小: {total_size / (1024**3):.2f} GB")
        print(f"总时长: {total_duration / 3600:.1f} 小时")
        print(f"数据库: {self.db_path}")


def main():
    parser = argparse.ArgumentParser(
        description='VideoDedup Enhanced - 视频去重工具（增强版）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描（标准模式）
  python videodedup_enhanced.py scan /path/to/videos
  
  # 严格模式扫描
  python videodedup_enhanced.py scan /path/to/videos --mode strict
  
  # 宽松模式（检测水印/裁剪版本）
  python videodedup_enhanced.py scan /path/to/videos --mode loose
  
  # 查找重复
  python videodedup_enhanced.py find
  
  # 跨库对比
  python videodedup_enhanced.py compare /path/to/external.db
        """
    )
    
    parser.add_argument('--db', default='videodedup.db', help='数据库路径')
    parser.add_argument('--workers', '-w', type=int, default=4, help='线程数')
    parser.add_argument('--mode', choices=['strict', 'standard', 'loose'], 
                       default='standard', help='相似度模式')
    
    subparsers = parser.add_subparsers(dest='command')
    
    # scan 命令
    scan_parser = subparsers.add_parser('scan', help='扫描视频')
    scan_parser.add_argument('paths', nargs='+', help='扫描路径')
    scan_parser.add_argument('--full', action='store_true', help='完整扫描')
    
    # find 命令
    find_parser = subparsers.add_parser('find', help='查找重复')
    find_parser.add_argument('--paths', nargs='+', help='指定路径')
    find_parser.add_argument('--output', '-o', default='duplicates.md', help='输出文件')
    find_parser.add_argument('--cross', action='store_true', help='跨目录对比')
    
    # compare 命令
    compare_parser = subparsers.add_parser('compare', help='与外部库对比')
    compare_parser.add_argument('external_db', help='外部数据库')
    compare_parser.add_argument('--output', '-o', default='cross_compare.md', help='输出文件')
    
    # stats 命令
    subparsers.add_parser('stats', help='显示统计')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    mode = SimilarityMode(args.mode)
    dedup = EnhancedVideoDedup(db_path=args.db, workers=args.workers, mode=mode)
    
    if args.command == 'scan':
        dedup.scan(paths=args.paths, incremental=not args.full)
    elif args.command == 'find':
        groups = dedup.find_duplicates(paths=args.paths, cross_compare=args.cross)
        if groups:
            print(f"\n发现 {len(groups)} 组重复视频")
            dedup.export_results(groups, args.output)
        else:
            print("\n未发现重复视频")
    elif args.command == 'compare':
        groups = dedup.compare_with_external(args.external_db, args.paths)
        if groups:
            print(f"\n发现 {len(groups)} 组跨库重复")
            dedup.export_results(groups, args.output)
        else:
            print("\n未发现跨库重复")
    elif args.command == 'stats':
        dedup.stats()


if __name__ == '__main__':
    main()
