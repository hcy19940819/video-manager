"""
视频扫描识别
"""
import cv2
import hashlib
import numpy as np
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict
import json

from .config import VIDEO_EXTENSIONS, THUMBS_DIR, SAMPLE_INTERVAL
from .database import Database
from .person_library import PersonLibrary


class VideoScanner:
    """视频扫描器"""
    
    def __init__(self, db: Database = None, person_lib: PersonLibrary = None):
        self.db = db or Database()
        self.person_lib = person_lib or PersonLibrary(self.db)
    
    def scan_directory(self, directory: str, recursive: bool = True) -> List[Path]:
        """扫描目录找视频文件"""
        video_files = []
        dir_path = Path(directory)
        
        if not dir_path.exists():
            print(f"✗ 目录不存在: {directory}")
            return video_files
        
        pattern = "**/*" if recursive else "*"
        
        for ext in VIDEO_EXTENSIONS:
            video_files.extend(dir_path.glob(f"{pattern}{ext}"))
            video_files.extend(dir_path.glob(f"{pattern}{ext.upper()}"))
        
        # 去重并排序
        video_files = sorted(set(video_files))
        
        return video_files
    
    def get_video_info(self, video_path: Path) -> Dict:
        """获取视频基本信息"""
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            return {}
        
        info = {
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'total_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        }
        
        info['duration'] = info['total_frames'] / info['fps'] if info['fps'] > 0 else 0
        
        cap.release()
        return info
    
    def calculate_md5(self, file_path: Path, chunk_size: int = 8192) -> str:
        """计算文件MD5"""
        hash_md5 = hashlib.md5()
        
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            print(f"✗ 计算MD5失败: {e}")
            return ""
    
    def generate_thumbnail(self, video_path: Path, output_path: Path = None) -> str:
        """生成视频缩略图"""
        if output_path is None:
            md5 = self.calculate_md5(video_path)
            output_path = THUMBS_DIR / f"{md5}.jpg"
        
        if output_path.exists():
            return str(output_path)
        
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            return ""
        
        # 取中间帧
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return ""
        
        # 调整大小
        height, width = frame.shape[:2]
        max_width = 320
        if width > max_width:
            ratio = max_width / width
            new_size = (max_width, int(height * ratio))
            frame = cv2.resize(frame, new_size)
        
        cv2.imwrite(str(output_path), frame)
        return str(output_path)
    
    def process_video(self, video_path: Path) -> Dict:
        """处理单个视频：提取信息+识别人物"""
        print(f"\n处理: {video_path.name}")
        
        # 检查是否已处理
        md5 = self.calculate_md5(video_path)
        existing = self.db.get_video_by_md5(md5)
        
        if existing:
            # 检查路径是否变化
            if existing['path'] != str(video_path.absolute()):
                print(f"  📍 路径更新: {existing['path']} -> {video_path}")
                self.db.update_video_path(md5, str(video_path.absolute()))
            else:
                print(f"  ⏭ 已处理过，跳过")
            return existing
        
        # 获取视频信息
        info = self.get_video_info(video_path)
        if not info:
            print(f"  ✗ 无法读取视频")
            return None
        
        print(f"  时长: {info['duration']:.1f}s, 分辨率: {info['width']}x{info['height']}")
        
        # 生成缩略图
        print(f"  生成缩略图...")
        thumbnail = self.generate_thumbnail(video_path)
        
        # 提取人脸并识别人物
        print(f"  识别人脸...")
        faces = self.person_lib.extract_video_faces(str(video_path), SAMPLE_INTERVAL)
        
        # 匹配人物
        matched_persons = []
        person_confidences = defaultdict(list)
        
        for face in faces:
            match = self.person_lib.match_face(face['embedding'])
            if match:
                name, confidence = match
                person_confidences[name].append(confidence)
        
        # 统计每个人物的出现次数和平均置信度
        for name, confidences in person_confidences.items():
            avg_conf = sum(confidences) / len(confidences)
            if len(confidences) >= 2 or avg_conf > 0.7:  # 至少出现2次或高置信度
                matched_persons.append(name)
                print(f"    ✓ 识别出: {name} (出现{len(confidences)}次, 置信度{avg_conf:.1%})")
        
        # 去重并保持顺序
        seen = set()
        unique_persons = []
        for p in matched_persons:
            if p not in seen:
                seen.add(p)
                unique_persons.append(p)
        
        # 保存到数据库
        video_id = self.db.add_video(
            md5=md5,
            path=str(video_path.absolute()),
            filename=video_path.name,
            size=video_path.stat().st_size,
            duration=info['duration'],
            width=info['width'],
            height=info['height'],
            thumbnail=thumbnail,
            face_count=len(faces),
            persons=unique_persons
        )
        
        # 保存出现记录
        for name in unique_persons:
            person = self.db.get_person_by_name(name)
            if person:
                confs = person_confidences[name]
                avg_conf = sum(confs) / len(confs)
                self.db.add_appearance(
                    video_id=video_id,
                    person_id=person['id'],
                    confidence=avg_conf,
                    face_count=len(confs)
                )
        
        print(f"  ✓ 完成: 识别出 {len(unique_persons)} 个人物")
        
        return {
            'id': video_id,
            'md5': md5,
            'path': str(video_path),
            'persons': unique_persons
        }
    
    def batch_scan(self, directory: str, recursive: bool = True):
        """批量扫描目录"""
        print(f"🔍 扫描目录: {directory}")
        
        # 先检查人物库
        persons = self.person_lib.scan_library()
        if not persons:
            print("\n⚠ 人物库为空！请先添加人物照片:")
            print(f"   在文件夹 {self.person_lib.library_dir} 下创建人物文件夹")
            print("   例如: 张三/, 李四/")
            print("   每人放3-5张清晰正面照片")
            return
        
        print(f"\n📚 人物库: {len(persons)} 个人物")
        for p in persons:
            print(f"   - {p['name']} ({p['image_count']}张照片)")
        
        # 扫描视频
        videos = self.scan_directory(directory, recursive)
        print(f"\n🎬 发现 {len(videos)} 个视频文件")
        
        if not videos:
            return
        
        # 处理每个视频
        processed = 0
        skipped = 0
        failed = 0
        
        for i, video_path in enumerate(videos, 1):
            print(f"\n[{i}/{len(videos)}] ", end="")
            
            result = self.process_video(video_path)
            
            if result:
                if result.get('id'):
                    processed += 1
                else:
                    skipped += 1
            else:
                failed += 1
        
        print(f"\n\n{'='*50}")
        print(f"✓ 扫描完成!")
        print(f"  新处理: {processed} 个")
        print(f"  已存在: {skipped} 个")
        print(f"  失败: {failed} 个")
        print(f"{'='*50}")
