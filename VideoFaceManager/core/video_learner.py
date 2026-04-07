"""
从已分类视频中学习人物特征
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import json
import shutil

from .config import VIDEO_EXTENSIONS, PERSON_LIBRARY_DIR, FACES_DIR
from .database import Database
from .person_library import PersonLibrary


class VideoLearner:
    """视频学习者 - 从已分类视频中提取人物特征"""
    
    def __init__(self, db: Database = None, person_lib: PersonLibrary = None):
        self.db = db or Database()
        self.person_lib = person_lib or PersonLibrary(self.db)
        self.faces_dir = FACES_DIR
        
    def scan_classified_videos(self, root_dir: str) -> Dict[str, List[Path]]:
        """
        扫描已分类的视频文件夹
        返回: {人物名: [视频路径列表]}
        """
        root = Path(root_dir)
        if not root.exists():
            print(f"✗ 目录不存在: {root}")
            return {}
        
        classified = {}
        
        # 遍历一级子文件夹（每个人物一个文件夹）
        for person_dir in root.iterdir():
            if not person_dir.is_dir():
                continue
            
            person_name = person_dir.name
            videos = []
            
            # 收集该文件夹下所有视频
            for ext in VIDEO_EXTENSIONS:
                videos.extend(person_dir.glob(f'*{ext}'))
                videos.extend(person_dir.glob(f'*{ext.upper()}'))
            
            if videos:
                classified[person_name] = videos
                print(f"  📁 {person_name}: 找到 {len(videos)} 个视频")
        
        return classified
    
    def learn_from_videos(self, root_dir: str, min_samples: int = 5, 
                          max_samples: int = 20, save_faces: bool = True) -> Dict[str, int]:
        """
        从已分类视频中学习人物特征
        
        Args:
            root_dir: 已分类视频根目录
            min_samples: 每个人物最少提取样本数
            max_samples: 每个人物最多提取样本数
            save_faces: 是否保存人脸截图
            
        Returns:
            {人物名: 提取的特征数量}
        """
        if not self.person_lib.face_app:
            print("✗ 人脸识别模型未加载")
            return {}
        
        print(f"\n🔍 扫描分类文件夹: {root_dir}")
        classified = self.scan_classified_videos(root_dir)
        
        if not classified:
            print("⚠ 没有找到已分类的视频文件夹")
            print("提示: 确保目录结构是")
            print("  根文件夹/")
            print("    ├── 张三/")
            print("    │   ├── video1.mp4")
            print("    │   └── video2.mp4")
            print("    └── 李四/")
            return {}
        
        print(f"\n📚 发现 {len(classified)} 个人物")
        
        results = {}
        
        for person_name, videos in classified.items():
            print(f"\n{'='*50}")
            print(f"👤 学习人物: {person_name}")
            print(f"{'='*50}")
            
            all_features = []
            saved_face_paths = []
            
            # 创建人物的人脸保存目录
            if save_faces:
                person_face_dir = self.faces_dir / person_name
                person_face_dir.mkdir(parents=True, exist_ok=True)
                # 清空旧截图
                for old in person_face_dir.glob('*.jpg'):
                    old.unlink()
            
            # 从每个视频中提取人脸
            for i, video_path in enumerate(videos, 1):
                print(f"\n  [{i}/{len(videos)}] 处理: {video_path.name}")
                
                features, face_count = self._extract_from_video(
                    video_path, person_name, 
                    max_samples - len(all_features),
                    save_faces
                )
                
                all_features.extend(features)
                
                if save_faces:
                    for j, feat in enumerate(features):
                        saved_face_paths.append(f"{person_name}/{person_name}_{i:02d}_{j:02d}.jpg")
                
                print(f"    提取了 {len(features)} 个人脸，累计: {len(all_features)}")
                
                # 达到上限就停止
                if len(all_features) >= max_samples:
                    print(f"    ✓ 已达到最大样本数 {max_samples}")
                    break
            
            # 检查是否达到最少样本数
            if len(all_features) < min_samples:
                print(f"  ⚠ 样本数不足 ({len(all_features)}/{min_samples})，跳过 {person_name}")
                continue
            
            # 保存到数据库
            # 同时保存到人物库文件夹
            person_dir = PERSON_LIBRARY_DIR / person_name
            person_dir.mkdir(exist_ok=True)
            
            person_id = self.db.add_person(person_name, all_features[:max_samples], saved_face_paths)
            results[person_name] = len(all_features[:max_samples])
            
            print(f"  ✓ {person_name} 学习完成，保存了 {len(all_features[:max_samples])} 个特征")
        
        print(f"\n{'='*50}")
        print(f"🎉 学习完成！共 {len(results)} 个人物")
        for name, count in results.items():
            print(f"   {name}: {count} 个特征")
        print(f"{'='*50}")
        
        return results
    
    def _extract_from_video(self, video_path: Path, person_name: str, 
                           max_needed: int, save_faces: bool) -> Tuple[List[List[float]], int]:
        """
        从单个视频中提取人脸特征
        
        Returns:
            (特征列表, 检测到的人脸总数)
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return [], 0
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # 根据视频时长调整采样间隔
        # 短视频(<30秒): 每秒采样
        # 中等(30-300秒): 每3秒采样
        # 长视频(>300秒): 每5秒采样
        if duration < 30:
            sample_interval = 1
        elif duration < 300:
            sample_interval = 3
        else:
            sample_interval = 5
        
        frame_interval = int(fps * sample_interval) if fps > 0 else 30
        
        features = []
        face_count = 0
        frame_idx = 0
        saved_count = 0
        
        while len(features) < max_needed:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1
            
            # 按间隔采样
            if frame_idx % frame_interval != 0:
                continue
            
            try:
                # 检测人脸
                faces = self.person_lib.face_app.get(frame)
                
                for face in faces:
                    face_count += 1
                    
                    # 只取最大的人脸（假设主要人物占画面最大）
                    if len(faces) > 1:
                        faces_sorted = sorted(faces, key=lambda x: 
                            (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
                        face = faces_sorted[0]
                    
                    # 检查人脸质量（置信度>0.8才要）
                    if face.det_score < 0.8:
                        continue
                    
                    features.append(face.embedding.tolist())
                    
                    # 保存人脸截图
                    if save_faces and saved_count < 10:  # 每个视频最多保存10张截图
                        self._save_face_crop(frame, face.bbox, person_name, 
                                            video_path.stem, saved_count)
                        saved_count += 1
                    
                    if len(features) >= max_needed:
                        break
                        
            except Exception as e:
                continue
        
        cap.release()
        return features, face_count
    
    def _save_face_crop(self, frame: np.ndarray, bbox: np.ndarray, 
                       person_name: str, video_name: str, idx: int):
        """保存人脸截图"""
        x1, y1, x2, y2 = map(int, bbox)
        
        # 添加20%边距
        h, w = frame.shape[:2]
        margin_x = int((x2 - x1) * 0.2)
        margin_y = int((y2 - y1) * 0.2)
        
        x1 = max(0, x1 - margin_x)
        y1 = max(0, y1 - margin_y)
        x2 = min(w, x2 + margin_x)
        y2 = min(h, y2 + margin_y)
        
        face_img = frame[y1:y2, x1:x2]
        
        # 调整大小为 150x150
        face_img = cv2.resize(face_img, (150, 150))
        
        # 保存
        save_path = self.faces_dir / person_name / f"{video_name}_{idx:02d}.jpg"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(save_path), face_img)
    
    def identify_videos(self, video_dir: str, output_dir: str = None,
                       auto_move: bool = False, min_confidence: float = 0.65) -> Dict[str, List[Dict]]:
        """
        识别未分类视频中的人物
        
        Args:
            video_dir: 未分类视频目录
            output_dir: 输出识别结果目录（可选）
            auto_move: 是否自动按人物移动视频（创建软链接）
            min_confidence: 最小置信度阈值
            
        Returns:
            {人物名: [{视频路径, 置信度, 时间戳}, ...]}
        """
        if not self.person_lib.face_app:
            print("✗ 人脸识别模型未加载")
            return {}
        
        # 检查是否有学习到的人物
        persons = self.db.get_all_persons()
        if not persons:
            print("✗ 人物库为空！请先运行 learn 命令学习人物特征")
            return {}
        
        print(f"\n🔍 识别视频: {video_dir}")
        print(f"📚 人物库: {len(persons)} 人")
        for p in persons:
            print(f"   - {p['name']} ({p['face_count']}个特征)")
        
        # 扫描视频
        root = Path(video_dir)
        videos = []
        for ext in VIDEO_EXTENSIONS:
            videos.extend(root.glob(f'*{ext}'))
            videos.extend(root.glob(f'*{ext.upper()}'))
            videos.extend(root.glob(f'**/*{ext}'))  # 包含子目录
            videos.extend(root.glob(f'**/*{ext.upper()}'))
        
        videos = list(set(videos))
        print(f"\n🎬 发现 {len(videos)} 个待识别视频")
        
        # 创建输出目录
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        
        # 创建分类目录（用于软链接）
        if auto_move and output_dir:
            for p in persons:
                (output_path / p['name']).mkdir(exist_ok=True)
            (output_path / "未识别").mkdir(exist_ok=True)
        
        results = defaultdict(list)
        
        for i, video_path in enumerate(videos, 1):
            print(f"\n  [{i}/{len(videos)}] {video_path.name}")
            
            # 识别视频
            identified = self._identify_single_video(video_path, min_confidence)
            
            if identified:
                for person_name, confidence, timestamps in identified:
                    results[person_name].append({
                        'video_path': str(video_path),
                        'video_name': video_path.name,
                        'confidence': confidence,
                        'timestamps': timestamps,  # 人物出现的时间点
                        'md5': self._calc_md5(video_path)
                    })
                    print(f"    ✓ 识别出: {person_name} (置信度{confidence:.1%}, {len(timestamps)}次出现)")
                    
                    # 创建软链接
                    if auto_move and output_dir:
                        link_path = output_path / person_name / video_path.name
                        if not link_path.exists():
                            try:
                                import os
                                os.symlink(video_path.absolute(), link_path)
                            except:
                                # Windows可能需要管理员权限，改用快捷方式或复制
                                shutil.copy2(video_path, link_path)
            else:
                print(f"    ○ 未识别出人物")
                if auto_move and output_dir:
                    dest = output_path / "未识别" / video_path.name
                    if not dest.exists():
                        shutil.copy2(video_path, dest)
        
        # 保存识别报告
        if output_dir:
            report_path = output_path / "识别报告.json"
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(dict(results), f, ensure_ascii=False, indent=2)
            print(f"\n📝 识别报告已保存: {report_path}")
        
        print(f"\n{'='*50}")
        print(f"🎉 识别完成！")
        for name, items in results.items():
            print(f"   {name}: {len(items)} 个视频")
        print(f"{'='*50}")
        
        return dict(results)
    
    def _identify_single_video(self, video_path: Path, min_confidence: float = 0.65) -> List[Tuple[str, float, List[float]]]:
        """
        识别单个视频中的人物
        
        Returns:
            [(人物名, 平均置信度, [时间点列表]), ...]
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # 采样策略：短视频全采，长视频稀疏采
        if duration < 60:
            sample_interval = 2  # 每2秒
        elif duration < 600:
            sample_interval = 5   # 每5秒
        else:
            sample_interval = 10  # 每10秒
        
        frame_interval = int(fps * sample_interval) if fps > 0 else 60
        
        # 收集每个人物的所有匹配
        person_matches = defaultdict(list)  # {人物名: [(置信度, 时间点), ...]}
        
        frame_idx = 0
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1
            
            if frame_idx % frame_interval != 0:
                continue
            
            frame_count += 1
            current_time = frame_idx / fps if fps > 0 else 0
            
            try:
                faces = self.person_lib.face_app.get(frame)
                
                for face in faces:
                    # 只取最大的人脸
                    if len(faces) > 1:
                        faces_sorted = sorted(faces, key=lambda x: 
                            (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
                        face = faces_sorted[0]
                    
                    # 匹配人物
                    match = self.person_lib.match_face(face.embedding.tolist(), min_confidence)
                    
                    if match:
                        person_name, confidence = match
                        person_matches[person_name].append((confidence, current_time))
                        
            except Exception as e:
                continue
        
        cap.release()
        
        # 整理结果：计算平均置信度和出现时间点
        results = []
        for person_name, matches in person_matches.items():
            if len(matches) < 2:  # 至少出现2次才算识别成功
                continue
            
            confidences = [m[0] for m in matches]
            timestamps = [m[1] for m in matches]
            avg_confidence = sum(confidences) / len(confidences)
            
            if avg_confidence >= min_confidence:
                results.append((person_name, avg_confidence, timestamps))
        
        # 按置信度排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def _calc_md5(self, file_path: Path) -> str:
        """计算文件MD5"""
        import hashlib
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return ""
