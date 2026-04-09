"""
数据库管理
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from .config import DB_PATH


class Database:
    """花名册数据库"""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            # 视频表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    md5 TEXT UNIQUE NOT NULL,
                    path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    size INTEGER DEFAULT 0,
                    duration REAL DEFAULT 0,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    thumbnail TEXT,
                    face_count INTEGER DEFAULT 0,
                    persons TEXT,  -- JSON数组 ["张三", "李四"]
                    status TEXT DEFAULT 'active',  -- active/deleted/moved
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 人物表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS persons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    face_count INTEGER DEFAULT 0,
                    face_features TEXT,  -- JSON格式特征向量
                    sample_images TEXT,  -- JSON数组照片路径
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 出现记录表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS appearances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    person_id INTEGER NOT NULL,
                    confidence REAL DEFAULT 0,
                    face_count INTEGER DEFAULT 0,
                    FOREIGN KEY (video_id) REFERENCES videos(id),
                    FOREIGN KEY (person_id) REFERENCES persons(id),
                    UNIQUE(video_id, person_id)
                )
            ''')
            
            # 创建索引
            conn.execute('CREATE INDEX IF NOT EXISTS idx_videos_md5 ON videos(md5)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_videos_persons ON videos(persons)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name)')
            conn.commit()
    
    # ==================== 视频操作 ====================
    
    def add_video(self, md5: str, path: str, filename: str, size: int = 0,
                  duration: float = 0, width: int = 0, height: int = 0,
                  thumbnail: str = "", face_count: int = 0, 
                  persons: List[str] = None) -> int:
        """添加视频记录，返回视频ID"""
        persons_json = json.dumps(persons or [], ensure_ascii=False)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT OR REPLACE INTO videos 
                (md5, path, filename, size, duration, width, height, 
                 thumbnail, face_count, persons, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (md5, path, filename, size, duration, width, height,
                  thumbnail, face_count, persons_json))
            conn.commit()
            return cursor.lastrowid
    
    def get_video_by_md5(self, md5: str) -> Optional[Dict]:
        """通过MD5获取视频"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT * FROM videos WHERE md5 = ?', (md5,)
            ).fetchone()
            if row:
                return dict(row)
            return None
    
    def get_video_by_id(self, video_id: int) -> Optional[Dict]:
        """通过ID获取视频"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT * FROM videos WHERE id = ?', (video_id,)
            ).fetchone()
            if row:
                return dict(row)
            return None
    
    def get_all_videos(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """获取所有视频"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sql = 'SELECT * FROM videos WHERE status = "active" ORDER BY id DESC'
            if limit:
                sql += f' LIMIT {limit} OFFSET {offset}'
            rows = conn.execute(sql).fetchall()
            return [dict(row) for row in rows]
    
    def update_video_persons(self, video_id: int, persons: List[str]):
        """更新视频的人物列表"""
        persons_json = json.dumps(persons, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE videos 
                SET persons = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (persons_json, video_id))
            conn.commit()
    
    def update_video_path(self, md5: str, new_path: str):
        """更新视频路径（文件移动时使用）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE videos 
                SET path = ?, filename = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE md5 = ?
            ''', (new_path, Path(new_path).name, md5))
            conn.commit()
    
    # ==================== 人物操作 ====================
    
    def add_person(self, name: str, face_features: List[List[float]] = None,
                   sample_images: List[str] = None) -> int:
        """添加人物，返回人物ID"""
        features_json = json.dumps(face_features or [])
        images_json = json.dumps(sample_images or [], ensure_ascii=False)
        face_count = len(face_features) if face_features else 0
        
        with sqlite3.connect(self.db_path) as conn:
            try:
                cursor = conn.execute('''
                    INSERT INTO persons (name, face_count, face_features, sample_images)
                    VALUES (?, ?, ?, ?)
                ''', (name, face_count, features_json, images_json))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # 人物已存在，更新
                person = self.get_person_by_name(name)
                if person and face_features:
                    existing_features = json.loads(person['face_features'] or '[]')
                    existing_features.extend(face_features)
                    existing_features = existing_features[:20]  # 最多保留20个特征
                    
                    existing_images = json.loads(person['sample_images'] or '[]')
                    if sample_images:
                        existing_images.extend(sample_images)
                    
                    conn.execute('''
                        UPDATE persons 
                        SET face_count = ?, face_features = ?, sample_images = ?
                        WHERE name = ?
                    ''', (len(existing_features), 
                          json.dumps(existing_features),
                          json.dumps(existing_images, ensure_ascii=False),
                          name))
                    conn.commit()
                    return person['id']
                return None
    
    def get_person_by_name(self, name: str) -> Optional[Dict]:
        """通过名称获取人物"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT * FROM persons WHERE name = ?', (name,)
            ).fetchone()
            if row:
                return dict(row)
            return None
    
    def get_person_by_id(self, person_id: int) -> Optional[Dict]:
        """通过ID获取人物"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT * FROM persons WHERE id = ?', (person_id,)
            ).fetchone()
            if row:
                return dict(row)
            return None
    
    def get_all_persons(self) -> List[Dict]:
        """获取所有人物"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM persons ORDER BY name').fetchall()
            return [dict(row) for row in rows]
    
    def delete_person(self, person_id: int):
        """删除人物"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM persons WHERE id = ?', (person_id,))
            conn.execute('DELETE FROM appearances WHERE person_id = ?', (person_id,))
            conn.commit()
    
    # ==================== 出现记录操作 ====================
    
    def add_appearance(self, video_id: int, person_id: int, 
                       confidence: float, face_count: int = 1):
        """添加人物出现记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO appearances 
                (video_id, person_id, confidence, face_count)
                VALUES (?, ?, ?, ?)
            ''', (video_id, person_id, confidence, face_count))
            conn.commit()
    
    def get_video_persons(self, video_id: int) -> List[Tuple[str, float]]:
        """获取视频中的所有人"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute('''
                SELECT p.name, a.confidence 
                FROM appearances a
                JOIN persons p ON a.person_id = p.id
                WHERE a.video_id = ?
                ORDER BY a.confidence DESC
            ''', (video_id,)).fetchall()
            return [(row[0], row[1]) for row in rows]
    
    def get_person_videos(self, person_id: int) -> List[Dict]:
        """获取人物出现的所有视频"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''
                SELECT v.*, a.confidence 
                FROM appearances a
                JOIN videos v ON a.video_id = v.id
                WHERE a.person_id = ? AND v.status = 'active'
                ORDER BY a.confidence DESC
            ''', (person_id,)).fetchall()
            return [dict(row) for row in rows]
    
    # ==================== 统计 ====================
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with sqlite3.connect(self.db_path) as conn:
            video_count = conn.execute(
                'SELECT COUNT(*) FROM videos WHERE status = "active"'
            ).fetchone()[0]
            
            person_count = conn.execute(
                'SELECT COUNT(*) FROM persons'
            ).fetchone()[0]
            
            total_size = conn.execute(
                'SELECT COALESCE(SUM(size), 0) FROM videos WHERE status = "active"'
            ).fetchone()[0]
            
            # 未识别人物的视频数
            unknown_count = conn.execute('''
                SELECT COUNT(*) FROM videos 
                WHERE status = 'active' AND (persons IS NULL OR persons = '[]')
            ''').fetchone()[0]
            
            return {
                'video_count': video_count,
                'person_count': person_count,
                'total_size': total_size,
                'unknown_count': unknown_count
            }
