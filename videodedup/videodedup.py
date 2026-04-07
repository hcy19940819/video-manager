#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoDedup - 视频快速去重工具
参考 DoubleKiller，专门针对视频优化

核心特性：
1. 多层指纹：文件大小 → 时长 → 快速pHash → 详细pHash序列
2. 增量对比：保存指纹数据库，只处理新文件
3. 多库对比：支持对比多个路径的指纹库
4. 相似视频识别：不同格式/编码/轻微剪辑的同内容视频
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
    # 简单的进度条替代
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            self.n = 0
            if desc:
                print(f"{desc}...")
        
        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            pass
        
        def update(self, n=1):
            self.n += n

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

# 相似度阈值
THRESHOLD_QUICK = 5      # 快速pHash汉明距离阈值（严格）
THRESHOLD_DETAIL = 10    # 详细pHash汉明距离阈值（宽松）
THRESHOLD_SSIM = 0.85    # SSIM相似度阈值

# 采样配置
QUICK_SAMPLE_INTERVAL = 30  # 快速模式每30秒采样一帧
DETAIL_KEYFRAME_MIN = 5     # 详细模式最少提取5个关键帧
DETAIL_KEYFRAME_MAX = 20    # 详细模式最多提取20个关键帧


# ==================== 数据模型 ====================

@dataclass
class VideoFingerprint:
    """视频指纹数据结构"""
    path: str
    size: int
    mtime: float
    duration: float = 0.0          # 视频时长(秒)
    width: int = 0                 # 分辨率宽
    height: int = 0                # 分辨率高
    fps: float = 0.0               # 帧率
    
    # 多层哈希
    quick_hash: str = ""           # 快速pHash（基于均匀采样）
    detail_hashes: List[str] = None # 详细pHash序列（基于关键帧）
    file_hash: str = ""            # 文件MD5（前1MB）
    
    # 元数据
    created_at: str = ""           # 指纹创建时间
    scan_version: int = 1          # 指纹算法版本
    
    def __post_init__(self):
        if self.detail_hashes is None:
            self.detail_hashes = []
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VideoFingerprint':
        return cls(**data)


@dataclass
class DuplicateGroup:
    """重复视频组"""
    group_id: int
    videos: List[VideoFingerprint]
    similarity_type: str  # 'identical', 'similar', 'maybe'
    reason: str


# ==================== 数据库管理 ====================

class FingerprintDB:
    """指纹数据库管理（SQLite）"""
    
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
                quick_hash TEXT,
                detail_hashes TEXT,
                file_hash TEXT,
                created_at TEXT,
                scan_version INTEGER DEFAULT 1
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quick_hash ON fingerprints(quick_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_size ON fingerprints(size)')
        
        # 表：扫描会话记录
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
    
    def get_fingerprint(self, path: str) -> Optional[VideoFingerprint]:
        """获取指定路径的指纹"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints WHERE path = ?', (path,))
        row = cursor.fetchone()
        if row:
            return self._row_to_fingerprint(row)
        return None
    
    def get_fingerprint_by_quick_hash(self, quick_hash: str) -> List[VideoFingerprint]:
        """通过快速哈希获取指纹列表"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints WHERE quick_hash = ?', (quick_hash,))
        return [self._row_to_fingerprint(row) for row in cursor.fetchall()]
    
    def get_all_fingerprints(self) -> List[VideoFingerprint]:
        """获取所有指纹"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints')
        return [self._row_to_fingerprint(row) for row in cursor.fetchall()]
    
    def get_fingerprints_by_size(self, size: int) -> List[VideoFingerprint]:
        """按文件大小获取指纹（预筛选）"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints WHERE size = ?', (size,))
        return [self._row_to_fingerprint(row) for row in cursor.fetchall()]
    
    def save_fingerprint(self, fp: VideoFingerprint) -> bool:
        """保存或更新指纹"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO fingerprints 
                (path, size, mtime, duration, width, height, fps, 
                 quick_hash, detail_hashes, file_hash, created_at, scan_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                fp.path, fp.size, fp.mtime, fp.duration, fp.width, fp.height, fp.fps,
                fp.quick_hash, json.dumps(fp.detail_hashes), fp.file_hash,
                fp.created_at, fp.scan_version
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"保存指纹失败 {fp.path}: {e}")
            return False
    
    def save_fingerprints_batch(self, fingerprints: List[VideoFingerprint]):
        """批量保存指纹"""
        cursor = self.conn.cursor()
        data = [(
            fp.path, fp.size, fp.mtime, fp.duration, fp.width, fp.height, fp.fps,
            fp.quick_hash, json.dumps(fp.detail_hashes), fp.file_hash,
            fp.created_at, fp.scan_version
        ) for fp in fingerprints]
        
        cursor.executemany('''
            INSERT OR REPLACE INTO fingerprints 
            (path, size, mtime, duration, width, height, fps,
             quick_hash, detail_hashes, file_hash, created_at, scan_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        self.conn.commit()
    
    def record_scan_session(self, scan_path: str, total: int, new: int, updated: int, duration: float):
        """记录扫描会话"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO scan_sessions (scan_path, scan_time, total_files, new_files, updated_files, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (scan_path, datetime.now().isoformat(), total, new, updated, duration))
        self.conn.commit()
    
    def _row_to_fingerprint(self, row: sqlite3.Row) -> VideoFingerprint:
        """数据库行转对象"""
        return VideoFingerprint(
            path=row['path'],
            size=row['size'],
            mtime=row['mtime'],
            duration=row['duration'],
            width=row['width'],
            height=row['height'],
            fps=row['fps'],
            quick_hash=row['quick_hash'] or '',
            detail_hashes=json.loads(row['detail_hashes']) if row['detail_hashes'] else [],
            file_hash=row['file_hash'] or '',
            created_at=row['created_at'] or '',
            scan_version=row['scan_version']
        )
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ==================== 视频处理核心 ====================

class VideoProcessor:
    """视频处理和指纹生成"""
    
    def __init__(self, quick_interval: int = QUICK_SAMPLE_INTERVAL, 
                 min_keyframes: int = DETAIL_KEYFRAME_MIN,
                 max_keyframes: int = DETAIL_KEYFRAME_MAX):
        self.quick_interval = quick_interval
        self.min_keyframes = min_keyframes
        self.max_keyframes = max_keyframes
        
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
    
    def extract_quick_hash(self, path: str) -> Optional[str]:
        """提取快速pHash（均匀采样）"""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return None
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # 采样时间点
        if duration < self.quick_interval * 2:
            # 短视频：取开头、中间、结尾
            sample_times = [0, duration / 2, duration * 0.9] if duration > 0 else [0]
        else:
            # 长视频：均匀采样
            sample_times = list(range(0, int(duration), self.quick_interval))
            if len(sample_times) > 10:
                sample_times = sample_times[:10]  # 最多10个采样点
        
        hashes = []
        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            if ret:
                phash = self._phash_frame(frame)
                if phash:
                    hashes.append(phash)
        
        cap.release()
        
        if not hashes:
            return None
        
        # 合并多个采样点的哈希
        return self._combine_hashes(hashes)
    
    def extract_detail_hashes(self, path: str) -> List[str]:
        """提取详细pHash序列（基于关键帧）"""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # 计算关键帧间隔
        if duration <= 0:
            cap.release()
            return []
        
        num_keyframes = max(self.min_keyframes, min(self.max_keyframes, int(duration / 10)))
        interval = duration / num_keyframes
        
        hashes = []
        for i in range(num_keyframes):
            t = i * interval + interval / 2  # 从中间开始
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            if ret:
                phash = self._phash_frame(frame)
                if phash:
                    hashes.append(phash)
        
        cap.release()
        return hashes
    
    def _phash_frame(self, frame) -> Optional[str]:
        """计算单帧的pHash"""
        try:
            # 转换为灰度图
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # 缩放为32x32
            resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_LANCZOS4)
            # DCT变换
            dct = cv2.dct(np.float32(resized))
            # 取左上角8x8低频分量
            dct_low = dct[:8, :8]
            # 计算均值（排除直流分量）
            avg = (dct_low.sum() - dct_low[0, 0]) / 63
            # 生成哈希
            hash_bits = (dct_low > avg).flatten().astype(int)
            # 转换为16进制字符串
            hash_str = ''.join(str(b) for b in hash_bits)
            return hex(int(hash_str, 2))[2:].zfill(16)
        except Exception:
            return None
    
    def _combine_hashes(self, hashes: List[str]) -> str:
        """合并多个哈希为一个"""
        if len(hashes) == 1:
            return hashes[0]
        # 简单拼接前几个哈希的关键位
        combined = ''.join(h[:8] for h in hashes[:3])
        return combined.ljust(16, '0')[:16]
    
    def compute_file_hash(self, path: str, max_size: int = 1024*1024) -> str:
        """计算文件前N字节的MD5"""
        try:
            hasher = hashlib.md5()
            with open(path, 'rb') as f:
                data = f.read(max_size)
                hasher.update(data)
            return hasher.hexdigest()
        except Exception:
            return ""


# ==================== 相似度计算 ====================

class SimilarityCalculator:
    """相似度计算工具"""
    
    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """计算两个哈希的汉明距离"""
        if not hash1 or not hash2 or len(hash1) != len(hash2):
            return float('inf')
        
        try:
            # 16进制转二进制
            bin1 = bin(int(hash1, 16))[2:].zfill(64)
            bin2 = bin(int(hash2, 16))[2:].zfill(64)
            return sum(c1 != c2 for c1, c2 in zip(bin1, bin2))
        except ValueError:
            return float('inf')
    
    @staticmethod
    def sequence_similarity(hashes1: List[str], hashes2: List[str]) -> float:
        """计算两个哈希序列的相似度"""
        if not hashes1 or not hashes2:
            return 0.0
        
        # 使用动态规划找最长公共子序列
        m, n = len(hashes1), len(hashes2)
        
        # 简化的相似度计算：基于汉明距离的匹配
        matches = 0
        threshold = 5  # 汉明距离小于5认为是匹配的
        
        used = set()
        for h1 in hashes1:
            best_match = None
            best_dist = float('inf')
            for j, h2 in enumerate(hashes2):
                if j in used:
                    continue
                dist = SimilarityCalculator.hamming_distance(h1, h2)
                if dist < best_dist:
                    best_dist = dist
                    best_match = j
            
            if best_match is not None and best_dist <= threshold:
                matches += 1
                used.add(best_match)
        
        return matches / max(m, n)
    
    @staticmethod
    def are_duplicates(fp1: VideoFingerprint, fp2: VideoFingerprint, 
                       threshold_quick: int = THRESHOLD_QUICK,
                       threshold_detail: int = THRESHOLD_DETAIL) -> Tuple[bool, str]:
        """判断两个视频是否为重复"""
        
        # 1. 文件大小完全相同 + 文件哈希相同 → 完全重复
        if fp1.size == fp2.size and fp1.file_hash and fp2.file_hash:
            if fp1.file_hash == fp2.file_hash:
                return True, "identical_file"
        
        # 2. 快速哈希比对
        if fp1.quick_hash and fp2.quick_hash:
            quick_dist = SimilarityCalculator.hamming_distance(fp1.quick_hash, fp2.quick_hash)
            
            # 快速哈希完全匹配
            if quick_dist <= 2:
                return True, "identical_quick_hash"
            
            # 快速哈希相似，进入详细比对
            if quick_dist <= threshold_quick:
                if fp1.detail_hashes and fp2.detail_hashes:
                    seq_sim = SimilarityCalculator.sequence_similarity(fp1.detail_hashes, fp2.detail_hashes)
                    
                    if seq_sim >= 0.9:
                        return True, "identical_content"
                    elif seq_sim >= 0.7:
                        return True, "similar_content"
        
        # 3. 时长和分辨率相近时的详细比对
        if (fp1.duration > 0 and fp2.duration > 0 and 
            abs(fp1.duration - fp2.duration) < 5 and  # 时长相差小于5秒
            fp1.width == fp2.width and fp1.height == fp2.height):
            
            if fp1.detail_hashes and fp2.detail_hashes:
                seq_sim = SimilarityCalculator.sequence_similarity(fp1.detail_hashes, fp2.detail_hashes)
                if seq_sim >= 0.85:
                    return True, "similar_resolution_duration"
        
        return False, ""


# ==================== 主程序 ====================

class VideoDedup:
    """视频去重主类"""
    
    def __init__(self, db_path: str = "videodedup.db", workers: int = 4):
        self.db_path = db_path
        self.workers = workers
        self.processor = VideoProcessor() if HAS_VIDEO else None
        self.similarity = SimilarityCalculator()
        self._scan_stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0}
    
    def scan(self, paths: List[str], incremental: bool = True, 
             update_existing: bool = False) -> List[VideoFingerprint]:
        """
        扫描路径生成指纹
        
        Args:
            paths: 要扫描的路径列表
            incremental: 是否增量扫描（跳过已存在的指纹）
            update_existing: 是否更新已存在的指纹（文件修改时间变化时）
        """
        # 收集所有视频文件
        video_files = []
        for path in paths:
            video_files.extend(self._collect_videos(path))
        
        self._scan_stats['total'] = len(video_files)
        
        # 过滤和分类
        with FingerprintDB(self.db_path) as db:
            to_process = []
            
            for filepath in video_files:
                existing = db.get_fingerprint(filepath)
                
                if existing is None:
                    # 新文件
                    to_process.append(filepath)
                    self._scan_stats['new'] += 1
                elif update_existing:
                    mtime = os.path.getmtime(filepath)
                    if mtime > existing.mtime:
                        # 文件已修改，更新
                        to_process.append(filepath)
                        self._scan_stats['updated'] += 1
                    else:
                        self._scan_stats['skipped'] += 1
                else:
                    self._scan_stats['skipped'] += 1
        
        if not to_process:
            print("没有新文件需要处理")
            return []
        
        print(f"\n扫描统计:")
        print(f"  总视频文件: {self._scan_stats['total']}")
        print(f"  新文件: {self._scan_stats['new']}")
        print(f"  待更新: {self._scan_stats['updated']}")
        print(f"  跳过: {self._scan_stats['skipped']}")
        print(f"\n开始处理 {len(to_process)} 个文件...")
        
        # 并行处理
        fingerprints = []
        start_time = datetime.now()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_path = {executor.submit(self._process_video, path): path 
                             for path in to_process}
            
            for future in tqdm(concurrent.futures.as_completed(future_to_path), 
                              total=len(to_process), desc="生成指纹"):
                path = future_to_path[future]
                try:
                    fp = future.result()
                    if fp:
                        fingerprints.append(fp)
                except Exception as e:
                    print(f"\n处理失败 {path}: {e}")
        
        # 批量保存
        if fingerprints:
            with FingerprintDB(self.db_path) as db:
                db.save_fingerprints_batch(fingerprints)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # 记录扫描会话
        with FingerprintDB(self.db_path) as db:
            db.record_scan_session(
                json.dumps(paths),
                self._scan_stats['total'],
                self._scan_stats['new'],
                self._scan_stats['updated'],
                duration
            )
        
        print(f"\n处理完成: {len(fingerprints)} 个指纹已保存")
        print(f"耗时: {duration:.1f} 秒")
        
        return fingerprints
    
    def _collect_videos(self, path: str) -> List[str]:
        """收集目录下的所有视频文件"""
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
    
    def _process_video(self, path: str) -> Optional[VideoFingerprint]:
        """处理单个视频文件生成指纹"""
        try:
            stat = os.stat(path)
            
            fp = VideoFingerprint(
                path=path,
                size=stat.st_size,
                mtime=stat.st_mtime
            )
            
            if self.processor:
                # 获取视频信息
                info = self.processor.get_video_info(path)
                if info:
                    fp.duration = info.get('duration', 0)
                    fp.width = info.get('width', 0)
                    fp.height = info.get('height', 0)
                    fp.fps = info.get('fps', 0)
                    
                    # 生成快速哈希
                    fp.quick_hash = self.processor.extract_quick_hash(path)
                    
                    # 生成详细哈希
                    fp.detail_hashes = self.processor.extract_detail_hashes(path)
                
                # 文件哈希（前1MB）
                fp.file_hash = self.processor.compute_file_hash(path)
            
            return fp
            
        except Exception as e:
            print(f"\n处理错误 {path}: {e}")
            return None
    
    def find_duplicates(self, paths: Optional[List[str]] = None,
                       cross_compare: bool = False) -> List[DuplicateGroup]:
        """
        查找重复视频
        
        Args:
            paths: 指定路径（None表示全部）
            cross_compare: 是否跨路径对比（不同目录间对比）
        """
        with FingerprintDB(self.db_path) as db:
            all_fps = db.get_all_fingerprints()
        
        if paths:
            # 过滤指定路径
            path_set = set()
            for p in paths:
                p_abs = str(Path(p).absolute())
                path_set.add(p_abs)
            
            all_fps = [fp for fp in all_fps 
                      if any(fp.path.startswith(p) for p in path_set)]
        
        print(f"\n共 {len(all_fps)} 个视频需要对比")
        
        # 按大小分组（预筛选）
        size_groups = defaultdict(list)
        for fp in all_fps:
            # 大小相近的文件归为一组（允许10%误差）
            size_key = fp.size // (1024 * 1024)  # 按MB分组
            size_groups[size_key].append(fp)
        
        # 查找重复组
        duplicate_groups = []
        processed = set()
        group_id = 0
        
        for size_key, fps in tqdm(size_groups.items(), desc="对比分组"):
            if len(fps) < 2:
                continue
            
            # 两两对比
            for i, fp1 in enumerate(fps):
                if fp1.path in processed:
                    continue
                
                group = [fp1]
                
                for fp2 in fps[i+1:]:
                    if fp2.path in processed:
                        continue
                    
                    is_dup, reason = self.similarity.are_duplicates(fp1, fp2)
                    
                    if is_dup:
                        group.append(fp2)
                        processed.add(fp2.path)
                
                if len(group) > 1:
                    processed.add(fp1.path)
                    group_id += 1
                    
                    # 确定相似度类型
                    sim_type = 'identical' if 'identical' in reason else 'similar'
                    
                    duplicate_groups.append(DuplicateGroup(
                        group_id=group_id,
                        videos=group,
                        similarity_type=sim_type,
                        reason=reason
                    ))
        
        return duplicate_groups
    
    def compare_with_external(self, external_db_path: str, 
                             current_paths: Optional[List[str]] = None) -> List[DuplicateGroup]:
        """
        与外部指纹库对比
        
        用于：对比不同路径/机器的指纹库
        """
        # 加载当前库
        with FingerprintDB(self.db_path) as db:
            current_fps = db.get_all_fingerprints()
        
        if current_paths:
            path_set = set(str(Path(p).absolute()) for p in current_paths)
            current_fps = [fp for fp in current_fps 
                          if any(fp.path.startswith(p) for p in path_set)]
        
        # 加载外部库
        with FingerprintDB(external_db_path) as ext_db:
            external_fps = ext_db.get_all_fingerprints()
        
        print(f"\n当前库: {len(current_fps)} 个视频")
        print(f"外部库: {len(external_fps)} 个视频")
        print("\n开始跨库对比...")
        
        # 跨库对比
        duplicate_groups = []
        group_id = 0
        
        for fp1 in tqdm(current_fps, desc="跨库对比"):
            group = [fp1]
            
            for fp2 in external_fps:
                is_dup, reason = self.similarity.are_duplicates(fp1, fp2)
                
                if is_dup:
                    group.append(fp2)
            
            if len(group) > 1:
                group_id += 1
                sim_type = 'identical' if 'identical' in reason else 'similar'
                
                duplicate_groups.append(DuplicateGroup(
                    group_id=group_id,
                    videos=group,
                    similarity_type=sim_type,
                    reason=f"cross_db:{reason}"
                ))
        
        return duplicate_groups
    
    def export_results(self, groups: List[DuplicateGroup], output_path: str):
        """导出结果到文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# VideoDedup 去重报告\n")
            f.write(f"生成时间: {datetime.now().isoformat()}\n")
            f.write(f"发现重复组: {len(groups)}\n\n")
            
            for group in groups:
                f.write(f"## 重复组 #{group.group_id} [{group.similarity_type}]\n")
                f.write(f"原因: {group.reason}\n")
                f.write(f"视频数量: {len(group.videos)}\n\n")
                
                # 按文件大小排序，保留最大的
                sorted_videos = sorted(group.videos, key=lambda x: x.size, reverse=True)
                
                f.write("| 建议 | 文件路径 | 大小 | 时长 | 分辨率 |\n")
                f.write("|------|----------|------|------|--------|\n")
                
                for i, v in enumerate(sorted_videos):
                    action = "保留" if i == 0 else "可删除"
                    size_mb = v.size / (1024 * 1024)
                    duration_str = f"{v.duration:.1f}s" if v.duration > 0 else "未知"
                    resolution = f"{v.width}x{v.height}" if v.width > 0 else "未知"
                    
                    f.write(f"| {action} | `{v.path}` | {size_mb:.1f}MB | {duration_str} | {resolution} |\n")
                
                f.write("\n---\n\n")
        
        print(f"\n结果已导出: {output_path}")
    
    def rename_duplicates(self, groups: List[DuplicateGroup], suffix_format: str = "_dup{id:03d}",
                         dry_run: bool = True) -> List[Dict]:
        """
        重命名重复文件，添加重复ID后缀
        
        Args:
            groups: 重复组列表
            suffix_format: 后缀格式，{id}会被替换为组ID
            dry_run: 是否为试运行（只显示不执行）
        
        Returns:
            重命名操作记录列表
        """
        operations = []
        
        for group in groups:
            dup_id = group.group_id
            suffix = suffix_format.format(id=dup_id)
            
            # 同一组内的所有视频都添加相同的后缀
            for video in group.videos:
                path = Path(video.path)
                
                # 生成新文件名: name_dup001.ext
                new_name = f"{path.stem}{suffix}{path.suffix}"
                new_path = path.parent / new_name
                
                # 处理文件名冲突
                counter = 1
                while new_path.exists() and new_path != path:
                    new_name = f"{path.stem}{suffix}_{counter}{path.suffix}"
                    new_path = path.parent / new_name
                    counter += 1
                
                operation = {
                    'group_id': dup_id,
                    'old_path': str(path),
                    'new_path': str(new_path),
                    'status': 'pending',
                    'error': None
                }
                
                if not dry_run:
                    try:
                        path.rename(new_path)
                        operation['status'] = 'success'
                        print(f"  [{dup_id:03d}] {path.name} -> {new_name}")
                    except Exception as e:
                        operation['status'] = 'failed'
                        operation['error'] = str(e)
                        print(f"  [{dup_id:03d}] 失败: {path.name} - {e}")
                else:
                    operation['status'] = 'dry_run'
                    print(f"  [{dup_id:03d}] {path.name} -> {new_name}")
                
                operations.append(operation)
        
        return operations
    
    def export_rename_script(self, groups: List[DuplicateGroup], output_path: str, 
                            platform: str = 'auto'):
        """
        导出重命名脚本（方便手动执行或审核）
        
        Args:
            groups: 重复组列表
            output_path: 脚本输出路径
            platform: 'windows', 'linux', 'mac', 'auto'
        """
        if platform == 'auto':
            import sys
            if sys.platform == 'win32':
                platform = 'windows'
            elif sys.platform == 'darwin':
                platform = 'mac'
            else:
                platform = 'linux'
        
        lines = []
        
        if platform == 'windows':
            lines.append('@echo off')
            lines.append('chcp 65001 >nul')  # UTF-8
            lines.append('echo VideoDedup 重命名脚本')
            lines.append('echo ====================')
            lines.append('')
            
            for group in groups:
                dup_id = group.group_id
                lines.append(f'echo [{dup_id:03d}] 组 ====================')
                
                for video in group.videos:
                    path = Path(video.path)
                    new_name = f"{path.stem}_dup{dup_id:03d}{path.suffix}"
                    new_path = path.parent / new_name
                    
                    # Windows batch rename
                    lines.append(f'ren "{path}" "{new_name}"')
                
                lines.append('')
            
            lines.append('echo 完成！')
            lines.append('pause')
            
        else:  # linux/mac
            lines.append('#!/bin/bash')
            lines.append('# VideoDedup 重命名脚本')
            lines.append('')
            lines.append("echo '开始重命名...'")
            lines.append('')
            
            for group in groups:
                dup_id = group.group_id
                lines.append(f"# [{dup_id:03d}] 组 ====================")
                
                for video in group.videos:
                    path = Path(video.path)
                    new_name = f"{path.stem}_dup{dup_id:03d}{path.suffix}"
                    
                    # Escape special chars
                    old_escaped = str(path).replace("'", "'\"'\"'")
                    new_escaped = new_name.replace("'", "'\"'\"'")
                    
                    lines.append(f"mv -n '{old_escaped}' '{new_escaped}' 2>/dev/null || echo '跳过: {old_escaped}'")
                
                lines.append('')
            
            lines.append("echo '完成！'")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        # 添加执行权限（Linux/Mac）
        if platform != 'windows':
            import stat
            os.chmod(output_path, os.stat(output_path).st_mode | stat.S_IXUSR)
        
        print(f"\n重命名脚本已导出: {output_path}")
        print(f"平台: {platform}")
        print(f"请审核后执行，或先使用 --dry-run 预览")
    
    def stats(self):
        """显示数据库统计信息"""
        with FingerprintDB(self.db_path) as db:
            all_fps = db.get_all_fingerprints()
        
        total_size = sum(fp.size for fp in all_fps)
        total_duration = sum(fp.duration for fp in all_fps)
        
        print(f"\n=== 数据库统计 ===")
        print(f"指纹数量: {len(all_fps)}")
        print(f"总大小: {total_size / (1024**3):.2f} GB")
        print(f"总时长: {total_duration / 3600:.1f} 小时")
        print(f"数据库路径: {self.db_path}")


def main():
    parser = argparse.ArgumentParser(
        description='VideoDedup - 视频快速去重工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描目录生成指纹
  python videodedup.py scan /path/to/videos
  
  # 增量扫描
  python videodedup.py scan /path/to/videos --incremental
  
  # 查找重复
  python videodedup.py find
  
  # 对比多个路径
  python videodedup.py find --paths /path1 /path2
  
  # 与外部指纹库对比
  python videodedup.py compare /path/to/external.db
  
  # 指定数据库位置
  python videodedup.py --db /custom/path.db scan /videos
        """
    )
    
    parser.add_argument('--db', default='videodedup.db', 
                       help='指纹数据库路径 (默认: videodedup.db)')
    parser.add_argument('--workers', '-w', type=int, default=4,
                       help='并行处理线程数 (默认: 4)')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # scan 命令
    scan_parser = subparsers.add_parser('scan', help='扫描视频生成指纹')
    scan_parser.add_argument('paths', nargs='+', help='要扫描的路径')
    scan_parser.add_argument('--full', action='store_true',
                            help='完整扫描（非增量）')
    scan_parser.add_argument('--update', action='store_true',
                            help='更新已修改的文件')
    
    # find 命令
    find_parser = subparsers.add_parser('find', help='查找重复视频')
    find_parser.add_argument('--paths', nargs='+',
                            help='指定路径（默认全部）')
    find_parser.add_argument('--output', '-o', default='duplicates.md',
                            help='结果输出路径 (默认: duplicates.md)')
    find_parser.add_argument('--cross', action='store_true',
                            help='跨目录对比模式')
    
    # compare 命令
    compare_parser = subparsers.add_parser('compare', 
                                          help='与外部指纹库对比')
    compare_parser.add_argument('external_db', help='外部数据库路径')
    compare_parser.add_argument('--paths', nargs='+',
                               help='当前库中指定的路径')
    compare_parser.add_argument('--output', '-o', default='cross_compare.md',
                               help='结果输出路径')
    
    # stats 命令
    stats_parser = subparsers.add_parser('stats', help='显示统计信息')
    
    # rename 命令
    rename_parser = subparsers.add_parser('rename', help='重命名重复文件（添加重复ID后缀）')
    rename_parser.add_argument('--groups', required=True, help='重复组JSON文件（由find命令生成）')
    rename_parser.add_argument('--execute', action='store_true', 
                              help='实际执行重命名（默认只预览）')
    rename_parser.add_argument('--suffix', default='_dup{id:03d}',
                              help='后缀格式，{id}会被替换为组ID（默认: _dup{id:03d}）')
    rename_parser.add_argument('--output', '-o', help='导出重命名脚本路径')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 初始化
    dedup = VideoDedup(db_path=args.db, workers=args.workers)
    
    # 执行命令
    if args.command == 'scan':
        dedup.scan(
            paths=args.paths,
            incremental=not args.full,
            update_existing=args.update
        )
    
    elif args.command == 'find':
        groups = dedup.find_duplicates(
            paths=args.paths,
            cross_compare=args.cross
        )
        
        if groups:
            print(f"\n发现 {len(groups)} 组重复视频")
            
            # 统计可释放空间
            total_savings = 0
            for g in groups:
                sizes = sorted([v.size for v in g.videos], reverse=True)
                total_savings += sum(sizes[1:])  # 除最大外都可删
            
            print(f"预计可释放空间: {total_savings / (1024**3):.2f} GB")
            
            dedup.export_results(groups, args.output)
            
            # 同时导出JSON格式的groups，供rename命令使用
            json_output = args.output.replace('.md', '.json')
            if json_output == args.output:
                json_output = args.output + '.json'
            
            groups_data = []
            for g in groups:
                groups_data.append({
                    'group_id': g.group_id,
                    'similarity_type': g.similarity_type,
                    'reason': g.reason,
                    'videos': [v.to_dict() for v in g.videos]
                })
            
            with open(json_output, 'w', encoding='utf-8') as f:
                json.dump(groups_data, f, ensure_ascii=False, indent=2)
            print(f"\n重复组数据已导出: {json_output}")
            print(f"使用: python videodedup.py rename --groups {json_output}")
            
            # 生成HTML可视化报告
            try:
                from html_report import export_html_report
                html_output = args.output.replace('.md', '.html')
                if html_output == args.output:
                    html_output = 'report.html'
                export_html_report(groups, html_output)
            except Exception as e:
                print(f"\nHTML报告生成失败: {e}")
                print("请确保安装了可选依赖: pip install opencv-python pillow")
            
        else:
            print("\n未发现重复视频")
    
    elif args.command == 'compare':
        groups = dedup.compare_with_external(
            external_db_path=args.external_db,
            current_paths=args.paths
        )
        
        if groups:
            print(f"\n发现 {len(groups)} 组跨库重复")
            dedup.export_results(groups, args.output)
        else:
            print("\n未发现跨库重复")
    
    elif args.command == 'stats':
        dedup.stats()
    
    elif args.command == 'rename':
        # 加载重复组数据
        with open(args.groups, 'r', encoding='utf-8') as f:
            groups_data = json.load(f)
        
        # 重建 DuplicateGroup 对象
        groups = []
        for g in groups_data:
            videos = [VideoFingerprint.from_dict(v) for v in g['videos']]
            groups.append(DuplicateGroup(
                group_id=g['group_id'],
                videos=videos,
                similarity_type=g['similarity_type'],
                reason=g['reason']
            ))
        
        print(f"加载了 {len(groups)} 组重复视频")
        print(f"后缀格式: {args.suffix}")
        print(f"模式: {'执行' if args.execute else '预览'}")
        print()
        
        # 执行或预览重命名
        operations = dedup.rename_duplicates(groups, suffix_format=args.suffix, dry_run=not args.execute)
        
        # 统计
        success_count = sum(1 for op in operations if op['status'] == ('success' if args.execute else 'dry_run'))
        failed_count = sum(1 for op in operations if op['status'] == 'failed')
        
        print(f"\n总计: {len(operations)} 个文件")
        print(f"成功: {success_count}")
        if failed_count > 0:
            print(f"失败: {failed_count}")
        
        # 导出脚本
        if args.output:
            dedup.export_rename_script(groups, args.output)
        
        if not args.execute:
            print("\n这是预览模式，没有实际执行重命名")
            print("使用 --execute 参数执行实际重命名")


if __name__ == '__main__':
    main()
