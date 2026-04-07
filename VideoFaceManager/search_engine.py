#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影库管家参考版 - 以图搜视频 + 语义搜索 + 高级筛选
"""
import sys
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import json

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.hybrid_library import HybridPersonLibrary
from core.database import Database


class ImageSearchEngine:
    """以图搜视频引擎 - 核心功能"""
    
    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.lib = HybridPersonLibrary(self.db)
    
    def search_by_image(self, image_path: str, min_confidence: float = 0.6) -> List[Dict]:
        """
        上传图片搜索包含该人物的视频
        
        Args:
            image_path: 查询图片路径
            min_confidence: 最小置信度
            
        Returns:
            [{video_path, video_name, confidence, timestamps, screenshots}, ...]
        """
        print(f"\n🔍 以图搜视频: {Path(image_path).name}")
        print("="*60)
        
        # 1. 提取查询图片的人脸特征
        query_features = self._extract_face_features(image_path)
        
        if not query_features:
            print("✗ 未在图片中检测到人脸")
            return []
        
        print(f"✓ 提取到 {len(query_features)} 个人脸特征")
        
        # 2. 扫描所有视频进行匹配
        from core.config import VIDEO_EXTENSIONS
        
        all_videos = []
        data_dir = Path("./data")  # 视频库目录
        for ext in VIDEO_EXTENSIONS:
            all_videos.extend(data_dir.rglob(f'*{ext}'))
            all_videos.extend(data_dir.rglob(f'*{ext.upper()}'))
        
        # 去重
        seen = set()
        unique_videos = []
        for v in all_videos:
            if str(v) not in seen:
                seen.add(str(v))
                unique_videos.append(v)
        
        print(f"📚 视频库共 {len(unique_videos)} 个视频")
        print("\n开始匹配...\n")
        
        # 3. 匹配每个视频
        results = []
        
        for i, video_path in enumerate(unique_videos, 1):
            print(f"  [{i}/{len(unique_videos)}] {video_path.name}...", end=" ")
            
            match_result = self._match_video(video_path, query_features, min_confidence)
            
            if match_result:
                results.append(match_result)
                print(f"✓ 匹配 ({match_result['confidence']:.1%})")
            else:
                print("✗")
        
        # 4. 排序返回
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        print(f"\n✅ 搜索完成，找到 {len(results)} 个匹配视频")
        return results
    
    def _extract_face_features(self, image_path: str) -> List[List[float]]:
        """从图片提取人脸特征"""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return []
            
            faces = self.lib.face_app.get(img)
            
            features = []
            for face in faces:
                if face.det_score >= 0.8:
                    features.append(face.embedding.tolist())
            
            return features
        except Exception as e:
            print(f"提取特征失败: {e}")
            return []
    
    def _match_video(self, video_path: Path, query_features: List[List[float]], 
                     min_confidence: float) -> Optional[Dict]:
        """匹配单个视频"""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # 采样策略
        if duration < 60:
            sample_interval = 3
        elif duration < 300:
            sample_interval = 5
        else:
            sample_interval = 10
        
        frame_interval = int(fps * sample_interval) if fps > 0 else 150
        
        # 匹配
        best_matches = []
        screenshots = []
        
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
                faces = self.lib.face_app.get(frame)
                
                for face in faces:
                    face_feat = face.embedding.tolist()
                    
                    # 与查询图片的所有人脸匹配
                    for query_feat in query_features:
                        sim = self._cosine_similarity(face_feat, query_feat)
                        
                        if sim >= min_confidence:
                            best_matches.append((sim, timestamp))
                            
                            # 保存截图（只保存最高置信度的几张）
                            if len(screenshots) < 3 and sim > 0.75:
                                screenshot = self._save_screenshot(
                                    frame, face.bbox, video_path, timestamp, sim
                                )
                                if screenshot:
                                    screenshots.append(screenshot)
                            break
                            
            except:
                continue
        
        cap.release()
        
        if not best_matches:
            return None
        
        # 计算平均置信度和出现次数
        confidences = [m[0] for m in best_matches]
        timestamps = sorted([m[1] for m in best_matches])
        
        avg_conf = sum(confidences) / len(confidences)
        
        if avg_conf < min_confidence:
            return None
        
        return {
            'video_path': str(video_path),
            'video_name': video_path.name,
            'confidence': avg_conf,
            'match_count': len(best_matches),
            'timestamps': timestamps[:5],
            'screenshots': screenshots,
            'duration': duration
        }
    
    def _save_screenshot(self, frame: np.ndarray, bbox: np.ndarray,
                        video_path: Path, timestamp: float, 
                        confidence: float) -> Optional[str]:
        """保存匹配截图"""
        try:
            from core.config import FACES_DIR
            
            # 创建搜索截图目录
            search_dir = FACES_DIR / "search_results"
            search_dir.mkdir(parents=True, exist_ok=True)
            
            # 裁剪人脸
            x1, y1, x2, y2 = map(int, bbox)
            h, w = frame.shape[:2]
            
            # 添加边距
            margin = int((y2 - y1) * 0.3)
            x1 = max(0, x1 - margin)
            y1 = max(0, y1 - margin)
            x2 = min(w, x2 + margin)
            y2 = min(h, y2 + margin)
            
            face_img = frame[y1:y2, x1:x2]
            face_img = cv2.resize(face_img, (200, 200))
            
            # 保存
            filename = f"{video_path.stem}_{timestamp:.1f}s_{confidence:.2f}.jpg"
            save_path = search_dir / filename
            cv2.imwrite(str(save_path), face_img)
            
            return str(save_path)
        except:
            return None
    
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """余弦相似度"""
        v1 = np.array(v1)
        v2 = np.array(v2)
        
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(v1, v2) / (norm1 * norm2))


class SemanticSearchEngine:
    """语义搜索引擎 - 用自然语言描述搜索视频"""
    
    def __init__(self, db: Database = None):
        self.db = db or Database()
    
    def search(self, query: str) -> List[Dict]:
        """
        语义搜索
        
        示例:
        - "找张三的视频"
        - "有李四和王五一起出现的"
        - "时长超过10分钟的"
        """
        print(f"\n🔍 语义搜索: \"{query}\"")
        print("="*60)
        
        # 解析查询意图
        intent = self._parse_query(query)
        
        print(f"识别意图: {intent}")
        
        # 执行搜索
        if intent['type'] == 'person':
            return self._search_by_person(intent['persons'])
        elif intent['type'] == 'duration':
            return self._search_by_duration(intent['min_duration'], intent.get('persons', []))
        else:
            # 默认关键词搜索
            return self._keyword_search(query)
    
    def _parse_query(self, query: str) -> Dict:
        """解析查询意图"""
        import re
        
        intent = {'type': 'keyword', 'original': query}
        
        # 提取人物名
        # 模式：找/有/包含 + 人名 + 的视频
        person_patterns = [
            r'找(.+?)的视频',
            r'有(.+?)(?:一起|同时)?',
            r'包含(.+?)',
            r'(.+?)出现',
        ]
        
        persons = []
        for pattern in person_patterns:
            matches = re.findall(pattern, query)
            for m in matches:
                # 分割多个人物
                for sep in ['和', '与', '、', ',']:
                    if sep in m:
                        persons.extend([p.strip() for p in m.split(sep)])
                        break
                else:
                    persons.append(m.strip())
        
        if persons:
            intent['type'] = 'person'
            intent['persons'] = list(set(persons))  # 去重
        
        # 提取时长
        duration_pattern = r'(\d+)\s*(分钟|min|小时|h)'
        duration_match = re.search(duration_pattern, query)
        if duration_match:
            value = int(duration_match.group(1))
            unit = duration_match.group(2)
            
            if unit in ['小时', 'h']:
                value *= 3600
            else:
                value *= 60
            
            intent['type'] = 'duration'
            intent['min_duration'] = value
        
        return intent
    
    def _search_by_person(self, persons: List[str]) -> List[Dict]:
        """按人物搜索"""
        results = []
        
        # 从数据库查找包含这些人物的视频
        all_videos = self.db.get_all_videos()
        
        for video in all_videos:
            if not video.get('persons'):
                continue
            
            try:
                video_persons = json.loads(video['persons'])
            except:
                continue
            
            # 计算匹配度
            matched = []
            for p in persons:
                if any(p in vp for vp in video_persons):
                    matched.append(p)
            
            if matched:
                results.append({
                    'video': video,
                    'matched_persons': matched,
                    'match_score': len(matched) / len(persons)
                })
        
        # 排序：匹配越多越靠前
        results.sort(key=lambda x: x['match_score'], reverse=True)
        
        print(f"找到 {len(results)} 个匹配视频")
        return results
    
    def _search_by_duration(self, min_duration: int, persons: List[str] = None) -> List[Dict]:
        """按时长搜索"""
        all_videos = self.db.get_all_videos()
        
        results = []
        for video in all_videos:
            if video.get('duration', 0) >= min_duration:
                # 如果还指定了人物，再检查人物
                if persons:
                    try:
                        video_persons = json.loads(video.get('persons', '[]'))
                        if not any(p in str(video_persons) for p in persons):
                            continue
                    except:
                        continue
                
                results.append({'video': video})
        
        print(f"找到 {len(results)} 个匹配视频")
        return results
    
    def _keyword_search(self, keyword: str) -> List[Dict]:
        """关键词搜索"""
        all_videos = self.db.get_all_videos()
        
        results = []
        keyword_lower = keyword.lower()
        
        for video in all_videos:
            score = 0
            
            # 匹配文件名
            if keyword_lower in video.get('filename', '').lower():
                score += 3
            
            # 匹配人物
            if keyword_lower in str(video.get('persons', '')).lower():
                score += 2
            
            if score > 0:
                results.append({
                    'video': video,
                    'match_score': score
                })
        
        results.sort(key=lambda x: x['match_score'], reverse=True)
        print(f"找到 {len(results)} 个匹配视频")
        return results


class VideoFilter:
    """高级筛选器"""
    
    FILTERS = {
        'duration': {
            '超短视频': (0, 60),
            '短视频': (60, 300),
            '中等': (300, 900),
            '长视频': (900, 1800),
            '超长': (1800, float('inf'))
        },
        'year': None,  # 动态从数据中计算
        'person_count': {
            '单人': (1, 1),
            '双人': (2, 2),
            '多人': (3, float('inf'))
        }
    }
    
    def __init__(self, db: Database = None):
        self.db = db or Database()
    
    def filter(self, **criteria) -> List[Dict]:
        """
        多维度筛选
        
        Args:
            duration: 'short'/'medium'/'long'
            min_duration: 秒
            max_duration: 秒
            persons: [人名列表]
            year: 年份
            has_persons: True/False
        """
        all_videos = self.db.get_all_videos()
        results = []
        
        for video in all_videos:
            if self._matches_criteria(video, criteria):
                results.append(video)
        
        return results
    
    def _matches_criteria(self, video: Dict, criteria: Dict) -> bool:
        """检查视频是否符合筛选条件"""
        # 时长筛选
        if 'min_duration' in criteria:
            if video.get('duration', 0) < criteria['min_duration']:
                return False
        
        if 'max_duration' in criteria:
            if video.get('duration', float('inf')) > criteria['max_duration']:
                return False
        
        # 人物筛选
        if 'persons' in criteria:
            try:
                video_persons = json.loads(video.get('persons', '[]'))
                if not all(p in video_persons for p in criteria['persons']):
                    return False
            except:
                return False
        
        if 'has_persons' in criteria:
            has = bool(video.get('persons') and video['persons'] != '[]')
            if has != criteria['has_persons']:
                return False
        
        # 年份筛选（从路径或文件名推断）
        if 'year' in criteria:
            import re
            text = f"{video.get('path', '')} {video.get('filename', '')}"
            years = re.findall(r'(19|20)\d{2}', text)
            if not years or int(years[0]) != criteria['year']:
                return False
        
        return True
    
    def get_stats(self) -> Dict:
        """获取视频库统计信息"""
        all_videos = self.db.get_all_videos()
        
        stats = {
            'total': len(all_videos),
            'total_duration': sum(v.get('duration', 0) for v in all_videos),
            'by_duration': defaultdict(int),
            'by_person_count': defaultdict(int),
            'persons': set()
        }
        
        for video in all_videos:
            # 时长分布
            duration = video.get('duration', 0)
            for name, (min_d, max_d) in self.FILTERS['duration'].items():
                if min_d <= duration < max_d:
                    stats['by_duration'][name] += 1
                    break
            
            # 人物数量分布
            try:
                persons = json.loads(video.get('persons', '[]'))
                person_count = len(persons)
                stats['persons'].update(persons)
            except:
                person_count = 0
            
            for name, (min_c, max_c) in self.FILTERS['person_count'].items():
                if min_c <= person_count <= max_c:
                    stats['by_person_count'][name] += 1
                    break
        
        stats['unique_persons'] = len(stats['persons'])
        del stats['persons']  # 删除set，不可JSON序列化
        
        return stats


# ========== CLI 接口 ==========

def image_search_cli():
    """以图搜视频命令行"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python image_search.py <图片路径>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    engine = ImageSearchEngine()
    results = engine.search_by_image(image_path, min_confidence=0.6)
    
    print("\n" + "="*60)
    print("搜索结果")
    print("="*60)
    
    if not results:
        print("未找到匹配视频")
        return
    
    for i, r in enumerate(results[:10], 1):  # 只显示前10个
        print(f"\n{i}. {r['video_name']}")
        print(f"   匹配度: {r['confidence']:.1%}")
        print(f"   匹配次数: {r['match_count']}次")
        print(f"   时间点: {', '.join(f'{t:.1f}s' for t in r['timestamps'])}")
        print(f"   路径: {r['video_path']}")
        
        if r['screenshots']:
            print(f"   截图: {len(r['screenshots'])}张")


def semantic_search_cli():
    """语义搜索命令行"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python semantic_search.py \"<搜索描述>\"")
        print("示例: python semantic_search.py \"找张三的视频\"")
        sys.exit(1)
    
    query = sys.argv[1]
    
    engine = SemanticSearchEngine()
    results = engine.search(query)
    
    print("\n" + "="*60)
    print("搜索结果")
    print("="*60)
    
    if not results:
        print("未找到匹配视频")
        return
    
    for i, r in enumerate(results[:10], 1):
        video = r['video']
        print(f"\n{i}. {video['filename']}")
        
        if 'matched_persons' in r:
            print(f"   匹配人物: {', '.join(r['matched_persons'])}")
        
        print(f"   时长: {video.get('duration', 0):.1f}秒")
        print(f"   路径: {video['path']}")


if __name__ == '__main__':
    image_search_cli()