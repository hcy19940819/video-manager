"""
综合识别引擎 - 整合反向学习 + 主动录入 + 纠正反馈
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import json

from .config import VIDEO_EXTENSIONS, FACES_DIR
from .database import Database
from .hybrid_library import HybridPersonLibrary


class HybridRecognizer:
    """混合识别器 - 支持多渠道特征的智能识别"""
    
    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.library = HybridPersonLibrary(self.db)
    
    def build_library(self, classified_videos: str = None, 
                      photo_library: str = None):
        """
        构建混合人物库
        
        Args:
            classified_videos: 已分类视频文件夹路径
            photo_library: 照片库文件夹路径
        """
        print("\n" + "="*60)
        print("📚 构建混合人物库")
        print("="*60)
        
        # 1. 反向学习（视频）
        if classified_videos:
            self._learn_from_videos(classified_videos)
        
        # 2. 主动录入（照片）
        if photo_library:
            self._import_photos(photo_library)
        
        # 3. 显示统计
        self._show_library_stats()
    
    def _learn_from_videos(self, video_dir: str):
        """从视频学习"""
        print("\n🎬 反向学习阶段 - 从已分类视频学习")
        print("-"*60)
        
        root = Path(video_dir)
        if not root.exists():
            print(f"⚠ 目录不存在: {video_dir}")
            return
        
        # 扫描每个人物文件夹
        for person_dir in root.iterdir():
            if not person_dir.is_dir():
                continue
            
            person_name = person_dir.name
            videos = []
            for ext in VIDEO_EXTENSIONS:
                videos.extend(person_dir.glob(f'*{ext}'))
                videos.extend(person_dir.glob(f'*{ext.upper()}'))
            
            if not videos:
                continue
            
            print(f"\n👤 {person_name} - 处理 {len(videos)} 个视频")
            
            features = []
            for video_path in videos:
                feats = self._extract_from_video(str(video_path), max_samples=3)
                features.extend(feats)
                print(f"  {video_path.name}: {len(feats)}个特征")
            
            if features:
                self.library.add_features(
                    person_name, 
                    features[:15],  # 每人最多15个视频特征
                    HybridPersonLibrary.SOURCE_VIDEO,
                    {'video_count': len(videos)}
                )
    
    def _import_photos(self, photo_dir: str):
        """导入照片"""
        print("\n📸 主动录入阶段 - 导入参考照片")
        print("-"*60)
        
        root = Path(photo_dir)
        if not root.exists():
            print(f"⚠ 目录不存在: {photo_dir}")
            return
        
        for person_dir in root.iterdir():
            if not person_dir.is_dir():
                continue
            
            person_name = person_dir.name
            
            # 查找照片
            photos = []
            for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                photos.extend(person_dir.glob(f'*{ext}'))
                photos.extend(person_dir.glob(f'*{ext.upper()}'))
            
            if not photos:
                continue
            
            print(f"\n👤 {person_name} - 导入 {len(photos)} 张照片")
            
            features = []
            for photo_path in photos:
                feat = self._extract_from_photo(str(photo_path))
                if feat:
                    features.append(feat)
            
            if features:
                self.library.add_features(
                    person_name,
                    features,
                    HybridPersonLibrary.SOURCE_PHOTO,
                    {'photo_count': len(photos)}
                )
    
    def _extract_from_video(self, video_path: str, max_samples: int = 3) -> List[List[float]]:
        """从视频提取特征"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        features = []
        positions = [0.3, 0.5, 0.7]  # 30%, 50%, 70%
        
        for pos in positions[:max_samples]:
            frame_idx = int(total_frames * pos)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            
            ret, frame = cap.read()
            if not ret:
                continue
            
            try:
                faces = self.library.face_app.get(frame)
                if faces:
                    face = max(faces, key=lambda x: 
                              (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
                    if face.det_score >= 0.8:
                        features.append(face.embedding.tolist())
            except:
                continue
        
        cap.release()
        return features
    
    def _extract_from_photo(self, photo_path: str) -> Optional[List[float]]:
        """从照片提取特征"""
        try:
            img = cv2.imread(photo_path)
            if img is None:
                return None
            
            faces = self.library.face_app.get(img)
            if faces:
                # 取最大人脸
                face = max(faces, key=lambda x: 
                          (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
                if face.det_score >= 0.8:
                    return face.embedding.tolist()
        except:
            pass
        return None
    
    def _show_library_stats(self):
        """显示人物库统计"""
        print("\n" + "="*60)
        print("📊 人物库统计")
        print("="*60)
        
        persons = self.db.get_all_persons()
        print(f"共 {len(persons)} 个人物\n")
        
        for person in persons:
            stats = self.library.get_person_stats(person['name'])
            print(f"  {person['name']:12s}", end="")
            print(f"  特征: {stats['total_features']:2d}个", end="")
            print(f"  来源: ", end="")
            
            by_src = stats['by_source']
            sources = []
            if by_src.get('photo', 0) > 0:
                sources.append(f"照片{by_src['photo']}")
            if by_src.get('video', 0) > 0:
                sources.append(f"视频{by_src['video']}")
            if by_src.get('correct', 0) > 0:
                sources.append(f"纠正{by_src['correct']}")
            
            print(", ".join(sources) if sources else "无", end="")
            print(f"  可信度: {stats['confidence']}")
    
    def recognize(self, video_path: str, min_confidence: float = 0.6) -> List[Dict]:
        """
        识别视频中的所有人物
        
        Returns:
            [{name, confidence, source, timestamps}, ...]
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # 采样策略
        if duration < 60:
            sample_interval = 2
        elif duration < 300:
            sample_interval = 5
        else:
            sample_interval = 10
        
        frame_interval = int(fps * sample_interval) if fps > 0 else 60
        
        # 收集匹配
        matches = defaultdict(list)  # {person_name: [(confidence, timestamp, source), ...]}
        
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1
            if frame_idx % frame_interval != 0:
                continue
            
            timestamp = frame_idx / fps if fps > 0 else 0
            
            try:
                faces = self.library.face_app.get(frame)
                
                for face in faces:
                    # 匹配
                    match = self.library.match_face_weighted(
                        face.embedding.tolist(), 
                        threshold=0.5  # 低阈值先收集，后面再过滤
                    )
                    
                    if match:
                        person_name, conf, source = match
                        matches[person_name].append((conf, timestamp, source))
                        
            except:
                continue
        
        cap.release()
        
        # 整理结果
        results = []
        for person_name, data in matches.items():
            if len(data) < 2:  # 至少出现2次
                continue
            
            confidences = [d[0] for d in data]
            timestamps = sorted([d[1] for d in data])
            sources = [d[2] for d in data]
            
            avg_conf = sum(confidences) / len(confidences)
            
            if avg_conf >= min_confidence:
                # 确定主要来源
                source_counts = defaultdict(int)
                for s in sources:
                    source_counts[s] += 1
                main_source = max(source_counts, key=source_counts.get)
                
                results.append({
                    'name': person_name,
                    'confidence': avg_conf,
                    'source': main_source,
                    'appearances': len(timestamps),
                    'timestamps': timestamps[:5]  # 前5个时间点
                })
        
        # 按置信度排序
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        return results
    
    def batch_recognize(self, video_dir: str, output_dir: str = None,
                       min_confidence: float = 0.6, auto_organize: bool = False):
        """
        批量识别并可选自动整理
        
        Args:
            video_dir: 视频目录
            output_dir: 输出目录
            min_confidence: 最小置信度
            auto_organize: 是否自动按人物整理
        """
        print("\n" + "="*60)
        print("🔍 批量识别视频")
        print("="*60)
        
        # 扫描视频
        root = Path(video_dir)
        videos = []
        for ext in VIDEO_EXTENSIONS:
            videos.extend(root.glob(f'*{ext}'))
            videos.extend(root.glob(f'*{ext.upper()}'))
        
        videos = list(set(videos))
        print(f"\n发现 {len(videos)} 个视频\n")
        
        # 创建输出目录
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        
        # 识别每个视频
        all_results = {}
        
        for i, video_path in enumerate(videos, 1):
            print(f"[{i}/{len(videos)}] {video_path.name}...", end=" ")
            
            results = self.recognize(str(video_path), min_confidence)
            all_results[video_path.name] = results
            
            if results:
                names = [f"{r['name']}({r['confidence']:.0%})" for r in results]
                print(", ".join(names))
                
                # 自动整理
                if auto_organize and output_dir:
                    self._organize_video(video_path, results, output_path)
            else:
                print("未识别")
                
                if auto_organize and output_dir:
                    unknown_dir = output_path / "未识别"
                    unknown_dir.mkdir(exist_ok=True)
                    self._link_or_copy(video_path, unknown_dir / video_path.name)
        
        # 保存报告
        if output_dir:
            self._save_report(all_results, output_path)
        
        print("\n" + "="*60)
        print("✅ 识别完成!")
        if output_dir:
            print(f"输出目录: {output_path}")
        print("="*60)
    
    def _organize_video(self, video_path: Path, results: List[Dict], 
                       output_path: Path):
        """按识别结果整理视频"""
        # 取置信度最高的人物作为主要分类
        if not results:
            return
        
        main_person = results[0]['name']
        person_dir = output_path / main_person
        person_dir.mkdir(exist_ok=True)
        
        # 创建链接或复制
        dest = person_dir / video_path.name
        self._link_or_copy(video_path, dest)
        
        # 同时保存识别信息
        info_file = person_dir / f"{video_path.stem}.json"
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump({
                'video': video_path.name,
                'identified': results
            }, f, ensure_ascii=False, indent=2)
    
    def _link_or_copy(self, src: Path, dest: Path):
        """创建软链接或复制文件"""
        if dest.exists():
            return
        
        try:
            import os
            os.symlink(src.absolute(), dest)
        except:
            import shutil
            shutil.copy2(src, dest)
    
    def _save_report(self, results: Dict, output_path: Path):
        """保存识别报告"""
        # JSON报告
        report_file = output_path / "识别报告.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # 文本报告
        txt_file = output_path / "人物标签.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("视频人物识别报告\n")
            f.write("="*60 + "\n\n")
            
            for video_name, persons in results.items():
                f.write(f"📹 {video_name}\n")
                if persons:
                    for p in persons:
                        f.write(f"   👤 {p['name']}: {p['confidence']:.1%} "
                               f"(来源:{p['source']}, 出现{p['appearances']}次)\n")
                else:
                    f.write("   ❓ 未识别\n")
                f.write("\n")
        
        print(f"\n📝 报告已保存到 {output_path}")
