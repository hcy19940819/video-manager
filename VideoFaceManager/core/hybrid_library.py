"""
综合人物库管理器 - 支持多渠道特征融合
反向学习 + 主动录入 + 纠正反馈
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import json
import shutil
from datetime import datetime

from .config import PERSON_LIBRARY_DIR, FACES_DIR
from .database import Database


class HybridPersonLibrary:
    """
    混合人物库 - 支持多种特征来源
    
    特征来源权重:
    - 主动录入照片: 权重 1.2 (最准确)
    - 反向学习视频: 权重 1.0 (基准)
    - 纠正反馈: 权重 1.5 (用户确认过，最可信)
    """
    
    # 特征来源类型
    SOURCE_PHOTO = "photo"      # 主动录入照片
    SOURCE_VIDEO = "video"      # 反向学习视频
    SOURCE_CORRECT = "correct"  # 纠正确认
    
    # 权重配置
    WEIGHTS = {
        SOURCE_PHOTO: 1.2,
        SOURCE_VIDEO: 1.0,
        SOURCE_CORRECT: 1.5
    }
    
    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.library_dir = PERSON_LIBRARY_DIR
        self.faces_dir = FACES_DIR
        self._face_app = None
    
    @property
    def face_app(self):
        """延迟加载模型"""
        if self._face_app is None:
            try:
                from insightface.app import FaceAnalysis
                self._face_app = FaceAnalysis(name='buffalo_l', root='./models')
                self._face_app.prepare(ctx_id=0, det_size=(640, 640))
                print("✓ 人脸识别模型加载完成")
            except Exception as e:
                print(f"⚠ 模型加载失败: {e}")
                raise
        return self._face_app
    
    def add_features(self, person_name: str, features: List[List[float]], 
                     source: str, metadata: Dict = None):
        """
        添加人物特征（带来源标记）
        
        Args:
            person_name: 人物名
            features: 特征向量列表
            source: 来源类型 (photo/video/correct)
            metadata: 额外信息（如视频路径、时间点等）
        """
        # 获取现有人物
        person = self.db.get_person_by_name(person_name)
        
        # 准备新特征数据
        new_entries = []
        for feat in features:
            entry = {
                'feature': feat,
                'source': source,
                'weight': self.WEIGHTS.get(source, 1.0),
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            new_entries.append(entry)
        
        if person:
            # 合并现有特征
            existing = self._load_enhanced_features(person)
            existing.extend(new_entries)
            
            # 限制总特征数（保留权重高的）
            existing.sort(key=lambda x: x['weight'], reverse=True)
            existing = existing[:50]  # 最多保留50个特征
            
            # 保存
            self._save_enhanced_features(person_name, existing)
            
            # 更新数据库基础信息
            flat_features = [e['feature'] for e in existing]
            self.db.add_person(person_name, flat_features, 
                             [e.get('metadata', {}).get('path', '') for e in existing])
        else:
            # 创建新人物
            self._save_enhanced_features(person_name, new_entries)
            flat_features = [e['feature'] for e in new_entries]
            self.db.add_person(person_name, flat_features)
        
        print(f"✓ {person_name}: 添加 {len(features)} 个[{source}]特征")
    
    def _load_enhanced_features(self, person: Dict) -> List[Dict]:
        """加载增强特征（带权重）"""
        # 从单独文件加载
        feature_file = self.faces_dir / f"{person['name']}_features.json"
        if feature_file.exists():
            with open(feature_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 兼容旧格式：从数据库加载并转换
        if person.get('face_features'):
            features = json.loads(person['face_features'])
            return [{
                'feature': f,
                'source': self.SOURCE_VIDEO,
                'weight': 1.0,
                'timestamp': person.get('created_at', ''),
                'metadata': {}
            } for f in features]
        
        return []
    
    def _save_enhanced_features(self, person_name: str, entries: List[Dict]):
        """保存增强特征"""
        feature_file = self.faces_dir / f"{person_name}_features.json"
        with open(feature_file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    
    def match_face_weighted(self, face_features: List[float], 
                            threshold: float = 0.6) -> Optional[Tuple[str, float, str]]:
        """
        加权匹配人脸
        
        Returns:
            (人物名, 加权相似度, 主要来源) 或 None
        """
        if not face_features:
            return None
        
        persons = self.db.get_all_persons()
        if not persons:
            return None
        
        best_match = None
        best_score = 0
        best_source = self.SOURCE_VIDEO
        
        for person in persons:
            entries = self._load_enhanced_features(person)
            if not entries:
                continue
            
            # 计算加权相似度
            weighted_scores = []
            for entry in entries:
                sim = self._cosine_similarity(face_features, entry['feature'])
                weighted_sim = sim * entry['weight']
                weighted_scores.append((weighted_sim, entry['source']))
            
            # 取最高加权相似度
            if weighted_scores:
                max_sim, source = max(weighted_scores, key=lambda x: x[0])
                if max_sim > best_score:
                    best_score = max_sim
                    best_match = person['name']
                    best_source = source
        
        # 归一化回0-1范围（权重可能使分数>1）
        normalized_score = min(best_score / 1.5, 1.0)
        
        if normalized_score >= threshold:
            return (best_match, normalized_score, best_source)
        return None
    
    def add_correction(self, video_path: str, person_name: str, 
                       is_positive: bool = True):
        """
        添加纠正反馈
        
        Args:
            video_path: 视频路径
            person_name: 人物名
            is_positive: True=确认正确, False=标记错误
        """
        # 从视频中提取特征作为纠正样本
        if is_positive:
            # 正样本：用户确认这是该人物
            features = self._extract_features_from_video(video_path, max_samples=5)
            if features:
                self.add_features(person_name, features, self.SOURCE_CORRECT, {
                    'path': video_path,
                    'type': 'user_correction'
                })
                print(f"✓ 已记录正反馈: {person_name} @ {Path(video_path).name}")
        else:
            # 负样本：用户标记错误
            # 记录到数据库用于后续排除
            self._record_negative_sample(video_path, person_name)
            print(f"✓ 已记录负反馈: 非{person_name} @ {Path(video_path).name}")
    
    def _extract_features_from_video(self, video_path: str, 
                                     max_samples: int = 5) -> List[List[float]]:
        """从视频提取特征"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 均匀采样
        features = []
        positions = [0.2, 0.4, 0.5, 0.6, 0.8]  # 视频进度20%,40%...
        
        for pos in positions[:max_samples]:
            frame_idx = int(total_frames * pos)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            
            ret, frame = cap.read()
            if not ret:
                continue
            
            try:
                faces = self.face_app.get(frame)
                if faces:
                    # 取最大人脸
                    face = max(faces, key=lambda x: 
                              (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
                    if face.det_score >= 0.8:
                        features.append(face.embedding.tolist())
            except:
                continue
        
        cap.release()
        return features
    
    def _record_negative_sample(self, video_path: str, person_name: str):
        """记录负样本"""
        # 保存到单独文件
        neg_file = self.faces_dir / "negative_samples.json"
        negatives = []
        if neg_file.exists():
            with open(neg_file, 'r', encoding='utf-8') as f:
                negatives = json.load(f)
        
        negatives.append({
            'video_path': video_path,
            'wrong_person': person_name,
            'timestamp': datetime.now().isoformat()
        })
        
        with open(neg_file, 'w', encoding='utf-8') as f:
            json.dump(negatives, f, ensure_ascii=False, indent=2)
    
    def get_person_stats(self, person_name: str) -> Dict:
        """获取人物统计信息"""
        person = self.db.get_person_by_name(person_name)
        if not person:
            return {}
        
        entries = self._load_enhanced_features(person)
        
        stats = {
            'name': person_name,
            'total_features': len(entries),
            'by_source': defaultdict(int),
            'avg_weight': 0,
            'confidence': '未知'
        }
        
        if entries:
            for e in entries:
                stats['by_source'][e['source']] += 1
            stats['avg_weight'] = sum(e['weight'] for e in entries) / len(entries)
            
            # 可信度评估
            correct_count = stats['by_source'].get(self.SOURCE_CORRECT, 0)
            photo_count = stats['by_source'].get(self.SOURCE_PHOTO, 0)
            if correct_count >= 5:
                stats['confidence'] = '高'
            elif photo_count >= 3 or correct_count >= 2:
                stats['confidence'] = '中'
            else:
                stats['confidence'] = '低'
        
        return stats
    
    def merge_similar_persons(self, person1: str, person2: str, 
                              new_name: str = None):
        """合并相似人物（如果发现是同一人）"""
        p1 = self.db.get_person_by_name(person1)
        p2 = self.db.get_person_by_name(person2)
        
        if not p1 or not p2:
            return False
        
        entries1 = self._load_enhanced_features(p1)
        entries2 = self._load_enhanced_features(p2)
        
        # 合并特征
        merged = entries1 + entries2
        merged_name = new_name or person1
        
        # 保存合并后的特征
        self._save_enhanced_features(merged_name, merged)
        
        # 更新数据库
        flat_features = [e['feature'] for e in merged]
        self.db.add_person(merged_name, flat_features)
        
        # 删除旧人物
        if person2 != merged_name:
            self.db.delete_person(p2['id'])
            print(f"✓ 已合并 {person1} + {person2} -> {merged_name}")
        
        return True
    
    def export_person_data(self, person_name: str, output_dir: str):
        """导出人物数据（用于备份或迁移）"""
        person = self.db.get_person_by_name(person_name)
        if not person:
            return False
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        entries = self._load_enhanced_features(person)
        
        export_data = {
            'name': person_name,
            'export_time': datetime.now().isoformat(),
            'features': entries,
            'stats': self.get_person_stats(person_name)
        }
        
        export_file = output_path / f"{person_name}.json"
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已导出: {export_file}")
        return True
    
    def import_person_data(self, import_file: str) -> bool:
        """导入人物数据"""
        import_path = Path(import_file)
        if not import_path.exists():
            return False
        
        with open(import_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        person_name = data['name']
        entries = data['features']
        
        self._save_enhanced_features(person_name, entries)
        
        flat_features = [e['feature'] for e in entries]
        self.db.add_person(person_name, flat_features)
        
        print(f"✓ 已导入: {person_name} ({len(entries)}个特征)")
        return True
    
    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度"""
        v1 = np.array(v1)
        v2 = np.array(v2)
        
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(v1, v2) / (norm1 * norm2))
