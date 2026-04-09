#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoDedup Fast - 极速扫描版
优化点：
1. 单帧采样（而非10帧）
2. 平均哈希aHash（比pHash快3倍）
3. 跳帧读取（减少解码开销）
4. 内存缓存视频句柄

适合：快速初筛，追求速度
"""
import os
import sys
import json
import sqlite3
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import concurrent.futures

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
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def update(self, n=1): pass

try:
    import cv2
    import numpy as np
    from PIL import Image
    HAS_VIDEO = True
except ImportError:
    HAS_VIDEO = False
    print("警告: 未安装 opencv-python")


VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'}

# ============ 极速配置 ============
FAST_SAMPLE_COUNT = 1       # 只采1帧（原10帧）
FAST_RESIZE_SIZE = 16       # 缩小到16x16（原32x32）
SKIP_FRAMES = 5             # 每隔5帧读一帧


@dataclass
class FastFingerprint:
    """精简指纹结构"""
    path: str
    size: int
    mtime: float
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    fast_hash: str = ""        # 单帧aHash
    file_hash: str = ""        # 前1MB MD5
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return asdict(self)


class FastVideoProcessor:
    """极速视频处理器"""
    
    def __init__(self):
        if not HAS_VIDEO:
            raise RuntimeError("需要安装 opencv-python")
    
    def get_video_info(self, path: str) -> Dict:
        """获取视频信息（快速版）"""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return {}
        
        info = {
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'total_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        }
        
        if info['fps'] > 0:
            info['duration'] = info['total_frames'] / info['fps']
        else:
            info['duration'] = 0
        
        cap.release()
        return info
    
    def extract_fast_hash(self, path: str) -> Optional[str]:
        """
        极速哈希：只采样1帧，aHash算法
        比pHash快3-5倍
        """
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return None
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 只采一帧：从中间位置
        if total_frames > 0:
            target_frame = total_frames // 2
        else:
            target_frame = 0
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        
        # 跳过几帧（关键帧更稳定）
        for _ in range(SKIP_FRAMES):
            cap.grab()
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return None
        
        # aHash算法（比pHash快）
        return self._ahash_frame(frame)
    
    def _ahash_frame(self, frame) -> Optional[str]:
        """
        平均哈希（Average Hash）- 比pHash快3倍
        步骤：
        1. 转灰度
        2. 缩小到16x16
        3. 计算平均亮度
        4. 每个像素与平均比较，生成0/1
        """
        try:
            # 转灰度
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # 快速缩小（插值方法影响速度）
            resized = cv2.resize(gray, (FAST_RESIZE_SIZE, FAST_RESIZE_SIZE), 
                                interpolation=cv2.INTER_LINEAR)
            # 计算平均值
            avg = resized.mean()
            # 二值化
            hash_bits = (resized > avg).flatten().astype(int)
            # 转16进制（16x16=256位=64个16进制字符）
            hash_str = ''.join(str(b) for b in hash_bits)
            return hex(int(hash_str, 2))[2:].zfill(64)
        except Exception:
            return None
    
    def compute_file_hash(self, path: str, max_size: int = 1024*1024) -> str:
        """文件前1MB MD5"""
        try:
            hasher = hashlib.md5()
            with open(path, 'rb') as f:
                hasher.update(f.read(max_size))
            return hasher.hexdigest()
        except Exception:
            return ""


class FastFingerprintDB:
    """极速版数据库（简化结构）"""
    
    def __init__(self, db_path: str = "videodedup_fast.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                duration REAL DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                fps REAL DEFAULT 0,
                fast_hash TEXT,
                file_hash TEXT,
                created_at TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fast_hash ON fingerprints(fast_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_size ON fingerprints(size)')
        self.conn.commit()
    
    def save_batch(self, fingerprints: List[FastFingerprint]):
        """批量保存"""
        cursor = self.conn.cursor()
        data = [(
            fp.path, fp.size, fp.mtime, fp.duration, fp.width, fp.height, fp.fps,
            fp.fast_hash, fp.file_hash, fp.created_at
        ) for fp in fingerprints]
        
        cursor.executemany('''
            INSERT OR REPLACE INTO fingerprints 
            (path, size, mtime, duration, width, height, fps, fast_hash, file_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        self.conn.commit()
    
    def get_all(self) -> List[FastFingerprint]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM fingerprints')
        rows = cursor.fetchall()
        return [FastFingerprint(
            path=r['path'], size=r['size'], mtime=r['mtime'],
            duration=r['duration'], width=r['width'], height=r['height'], fps=r['fps'],
            fast_hash=r['fast_hash'] or '', file_hash=r['file_hash'] or '',
            created_at=r['created_at'] or ''
        ) for r in rows]
    
    def close(self):
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class FastVideoDedup:
    """极速去重主类"""
    
    def __init__(self, db_path: str = "videodedup_fast.db", workers: int = 8):
        self.db_path = db_path
        self.workers = workers
        self.processor = FastVideoProcessor() if HAS_VIDEO else None
    
    def scan(self, paths: List[str]) -> List[FastFingerprint]:
        """极速扫描"""
        # 收集视频
        video_files = []
        for path in paths:
            p = Path(path)
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                video_files.append(str(p.absolute()))
            elif p.is_dir():
                for ext in VIDEO_EXTENSIONS:
                    video_files.extend(str(f.absolute()) for f in p.rglob(f"*{ext}"))
        
        print(f"发现 {len(video_files)} 个视频文件")
        
        # 过滤已存在的
        with FastFingerprintDB(self.db_path) as db:
            existing_paths = {r['path'] for r in db.conn.execute('SELECT path FROM fingerprints')}
        
        to_process = [p for p in video_files if p not in existing_paths]
        print(f"需要处理: {len(to_process)} 个（跳过 {len(video_files) - len(to_process)} 个已存在）")
        
        if not to_process:
            return []
        
        # 并行处理
        fingerprints = []
        start = datetime.now()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._process_one, p): p for p in to_process}
            
            for future in tqdm(concurrent.futures.as_completed(futures), 
                              total=len(to_process), desc="极速扫描"):
                result = future.result()
                if result:
                    fingerprints.append(result)
        
        # 批量保存
        if fingerprints:
            with FastFingerprintDB(self.db_path) as db:
                db.save_batch(fingerprints)
        
        duration = (datetime.now() - start).total_seconds()
        speed = len(to_process) / duration if duration > 0 else 0
        
        print(f"\n完成！处理 {len(fingerprints)} 个视频")
        print(f"耗时: {duration:.1f} 秒 ({speed:.1f} 个/秒)")
        
        return fingerprints
    
    def _process_one(self, path: str) -> Optional[FastFingerprint]:
        """处理单个视频"""
        try:
            stat = os.stat(path)
            fp = FastFingerprint(
                path=path,
                size=stat.st_size,
                mtime=stat.st_mtime
            )
            
            if self.processor:
                info = self.processor.get_video_info(path)
                if info:
                    fp.duration = info.get('duration', 0)
                    fp.width = info.get('width', 0)
                    fp.height = info.get('height', 0)
                    fp.fps = info.get('fps', 0)
                
                # 极速哈希
                fp.fast_hash = self.processor.extract_fast_hash(path)
                fp.file_hash = self.processor.compute_file_hash(path)
            
            return fp
        except Exception as e:
            return None
    
    def find_duplicates(self, threshold: int = 10) -> List[Dict]:
        """
        查找重复（汉明距离阈值）
        threshold: 哈希差异位数，越小越严格
        """
        with FastFingerprintDB(self.db_path) as db:
            all_fps = db.get_all()
        
        print(f"\n共 {len(all_fps)} 个视频")
        
        # 按大小分组（预筛选）
        size_groups = defaultdict(list)
        for fp in all_fps:
            size_mb = fp.size // (1024 * 1024)
            size_groups[size_mb].append(fp)
        
        duplicates = []
        processed = set()
        
        for size_key, fps in tqdm(size_groups.items(), desc="查找重复"):
            if len(fps) < 2:
                continue
            
            for i, fp1 in enumerate(fps):
                if fp1.path in processed:
                    continue
                
                group = [fp1]
                
                for fp2 in fps[i+1:]:
                    if fp2.path in processed:
                        continue
                    
                    if self._is_duplicate(fp1, fp2, threshold):
                        group.append(fp2)
                        processed.add(fp2.path)
                
                if len(group) > 1:
                    processed.add(fp1.path)
                    duplicates.append({
                        'group_id': len(duplicates) + 1,
                        'videos': group,
                        'count': len(group)
                    })
        
        return duplicates
    
    def _is_duplicate(self, fp1: FastFingerprint, fp2: FastFingerprint, threshold: int) -> bool:
        """判断是否为重复"""
        # 文件大小相同 + 文件哈希相同 = 完全相同
        if fp1.size == fp2.size and fp1.file_hash == fp2.file_hash:
            return True
        
        # 哈希对比
        if fp1.fast_hash and fp2.fast_hash:
            dist = self._hamming_distance(fp1.fast_hash, fp2.fast_hash)
            if dist <= threshold:
                return True
        
        return False
    
    def _hamming_distance(self, h1: str, h2: str) -> int:
        """汉明距离"""
        if len(h1) != len(h2):
            return 999
        try:
            # 16进制转二进制比较
            bin1 = bin(int(h1, 16))[2:].zfill(256)
            bin2 = bin(int(h2, 16))[2:].zfill(256)
            return sum(c1 != c2 for c1, c2 in zip(bin1, bin2))
        except:
            return 999
    
    def export_results(self, duplicates: List[Dict], output: str = "duplicates_fast.md"):
        """导出结果"""
        with open(output, 'w', encoding='utf-8') as f:
            f.write(f"# 极速去重报告\n生成时间: {datetime.now().isoformat()}\n\n")
            f.write(f"发现 {len(duplicates)} 组重复\n\n")
            
            for dup in duplicates:
                f.write(f"## 重复组 #{dup['group_id']} ({dup['count']}个文件)\n\n")
                
                videos = sorted(dup['videos'], key=lambda x: x.size, reverse=True)
                
                f.write("| 建议 | 文件 | 大小 | 时长 |\n")
                f.write("|------|------|------|------|\n")
                
                for i, v in enumerate(videos):
                    action = "保留" if i == 0 else "删除"
                    size_mb = v.size / (1024**2)
                    duration = f"{v.duration:.1f}s" if v.duration > 0 else "未知"
                    f.write(f"| {action} | `{v.path}` | {size_mb:.1f}MB | {duration} |\n")
                
                f.write("\n---\n\n")
        
        print(f"结果已保存: {output}")


def main():
    parser = argparse.ArgumentParser(description='VideoDedup Fast - 极速扫描版')
    parser.add_argument('--db', default='videodedup_fast.db')
    parser.add_argument('--workers', '-w', type=int, default=8)
    
    sub = parser.add_subparsers(dest='cmd')
    
    scan_p = sub.add_parser('scan', help='极速扫描')
    scan_p.add_argument('paths', nargs='+')
    
    find_p = sub.add_parser('find', help='查找重复')
    find_p.add_argument('--threshold', '-t', type=int, default=10, help='汉明距离阈值')
    find_p.add_argument('--output', '-o', default='duplicates_fast.md')
    
    args = parser.parse_args()
    
    dedup = FastVideoDedup(args.db, args.workers)
    
    if args.cmd == 'scan':
        dedup.scan(args.paths)
    elif args.cmd == 'find':
        dups = dedup.find_duplicates(args.threshold)
        if dups:
            print(f"\n发现 {len(dups)} 组重复")
            total_size = sum(
                sum(v.size for v in d['videos'][1:]) / (1024**3)
                for d in dups
            )
            print(f"预计可释放: {total_size:.2f} GB")
            dedup.export_results(dups, args.output)
        else:
            print("未发现重复")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()