"""
人物库管理
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
from PIL import Image
import json

from .config import PERSON_LIBRARY_DIR, FACE_THUMB_SIZE
from .database import Database


class PersonLibrary:
    """人物库管理器"""
    
    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.library_dir = PERSON_LIBRARY_DIR
        self.face_detector = None
        self.face_encoder = None
        self._init_models()
    
    def _init_models(self):
        """初始化人脸识别模型"""
        try:
            import insightface
            from insightface.app import FaceAnalysis
            
            # 使用轻量级模型
            self.face_app = FaceAnalysis(name='buffalo_l', root='./models')
            self.face_app.prepare(ctx_id=0, det_size=(640, 640))
            print("✓ 人脸识别模型加载完成")
        except Exception as e:
            print(f"⚠ 模型加载失败: {e}")
            print("  首次使用会自动下载模型")
            self.face_app = None
    
    def scan_library(self) -> List[Dict]:
        """扫描人物库文件夹，返回人物列表"""
        persons = []
        
        if not self.library_dir.exists():
            return persons
        
        for person_dir in self.library_dir.iterdir():
            if person_dir.is_dir():
                name = person_dir.name
                # 查找照片文件
                images = []
                for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']:
                    images.extend(person_dir.glob(f'*{ext}'))
                    images.extend(person_dir.glob(f'*{ext.upper()}'))
                
                # 获取数据库中的人物信息
                db_person = self.db.get_person_by_name(name)
                
                persons.append({
                    'name': name,
                    'folder': str(person_dir),
                    'image_count': len(images),
                    'image_paths': [str(img) for img in images[:5]],  # 只显示前5张
                    'in_database': db_person is not None,
                    'face_count': db_person['face_count'] if db_person else 0
                })
        
        return sorted(persons, key=lambda x: x['name'])
    
    def create_person(self, name: str) -> Path:
        """创建新人物文件夹"""
        person_dir = self.library_dir / name
        person_dir.mkdir(parents=True, exist_ok=True)
        return person_dir
    
    def add_person_images(self, name: str, image_paths: List[str]) -> bool:
        """添加人物照片，并提取特征"""
        if not self.face_app:
            print("⚠ 人脸识别模型未加载")
            return False
        
        person_dir = self.library_dir / name
        person_dir.mkdir(exist_ok=True)
        
        all_features = []
        saved_images = []
        
        for img_path in image_paths:
            img_path = Path(img_path)
            if not img_path.exists():
                continue
            
            try:
                # 读取图片
                img = cv2.imread(str(img_path))
                if img is None:
                    continue
                
                # 检测人脸
                faces = self.face_app.get(img)
                
                if len(faces) == 0:
                    print(f"  未检测到人脸: {img_path.name}")
                    continue
                
                if len(faces) > 1:
                    print(f"  检测到多人，取最大人脸: {img_path.name}")
                    faces = sorted(faces, key=lambda x: x.bbox[2] - x.bbox[0], reverse=True)
                
                face = faces[0]
                features = face.embedding.tolist()
                all_features.append(features)
                
                # 保存照片到人物库
                save_name = f"{len(saved_images):03d}_{img_path.name}"
                save_path = person_dir / save_name
                
                # 复制并生成缩略图
                self._save_face_thumbnail(img, face.bbox, save_path)
                saved_images.append(str(save_path))
                
                print(f"  ✓ 已处理: {img_path.name}")
                
            except Exception as e:
                print(f"  ✗ 处理失败 {img_path.name}: {e}")
        
        if all_features:
            # 保存到数据库
            person_id = self.db.add_person(name, all_features, saved_images)
            print(f"✓ 人物 '{name}' 已添加，提取了 {len(all_features)} 个人脸特征")
            return True
        else:
            print(f"✗ 未能从照片中提取人脸: {name}")
            return False
    
    def _save_face_thumbnail(self, img: np.ndarray, bbox: np.ndarray, save_path: Path):
        """保存人脸缩略图"""
        x1, y1, x2, y2 = map(int, bbox)
        
        # 添加边距
        h, w = img.shape[:2]
        margin = int((y2 - y1) * 0.2)
        x1 = max(0, x1 - margin)
        y1 = max(0, y1 - margin)
        x2 = min(w, x2 + margin)
        y2 = min(h, y2 + margin)
        
        face_img = img[y1:y2, x1:x2]
        
        # 调整大小
        face_img = cv2.resize(face_img, (FACE_THUMB_SIZE, FACE_THUMB_SIZE))
        cv2.imwrite(str(save_path), face_img)
    
    def delete_person(self, name: str) -> bool:
        """删除人物"""
        import shutil
        
        person_dir = self.library_dir / name
        if person_dir.exists():
            shutil.rmtree(person_dir)
        
        person = self.db.get_person_by_name(name)
        if person:
            self.db.delete_person(person['id'])
            return True
        return False
    
    def get_person_face_features(self, name: str) -> Optional[List[List[float]]]:
        """获取人物的人脸特征"""
        person = self.db.get_person_by_name(name)
        if person and person['face_features']:
            return json.loads(person['face_features'])
        return None
    
    def match_face(self, face_features: List[float], threshold: float = 0.6) -> Optional[Tuple[str, float]]:
        """匹配人脸，返回（人物名，相似度）或None"""
        if not face_features:
            return None
        
        persons = self.db.get_all_persons()
        if not persons:
            return None
        
        best_match = None
        best_score = 0
        
        for person in persons:
            if not person['face_features']:
                continue
            
            person_features = json.loads(person['face_features'])
            if not person_features:
                continue
            
            # 计算与所有参考特征的最大相似度
            for ref_features in person_features:
                similarity = self._cosine_similarity(face_features, ref_features)
                if similarity > best_score:
                    best_score = similarity
                    best_match = person['name']
        
        if best_score >= threshold:
            return (best_match, best_score)
        return None
    
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度"""
        v1 = np.array(v1)
        v2 = np.array(v2)
        
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(v1, v2) / (norm1 * norm2))
    
    def extract_video_faces(self, video_path: str, sample_interval: int = 5) -> List[Dict]:
        """从视频中提取所有人脸"""
        if not self.face_app:
            print("⚠ 人脸识别模型未加载")
            return []
        
        faces_list = []
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            return faces_list
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        frame_interval = int(fps * sample_interval) if fps > 0 else 150
        
        frame_count = 0
        processed = 0
        
        print(f"  视频时长: {duration:.1f}秒, 采样间隔: {sample_interval}秒")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # 按间隔采样
            if frame_count % frame_interval != 0:
                continue
            
            try:
                faces = self.face_app.get(frame)
                
                for face in faces:
                    faces_list.append({
                        'embedding': face.embedding.tolist(),
                        'bbox': face.bbox.tolist(),
                        'confidence': float(face.det_score),
                        'frame_time': frame_count / fps if fps > 0 else 0
                    })
                
                processed += 1
                if processed % 10 == 0:
                    print(f"    已处理 {processed} 帧, 提取 {len(faces_list)} 个人脸")
                
                # 限制最大提取数量
                if len(faces_list) >= 100:
                    break
                    
            except Exception as e:
                continue
        
        cap.release()
        print(f"  ✓ 共提取 {len(faces_list)} 个人脸")
        
        return faces_list
