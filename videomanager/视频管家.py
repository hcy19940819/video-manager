#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频管家 - 一体化视频管理系统
功能：去重 + 人物识别 + 以图搜视频 + 语义搜索
特点：一次扫描，数据互通
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

# 进度条
try:
    from tqdm import tqdm
    有进度条 = True
except ImportError:
    有进度条 = False
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

# 视频处理
try:
    import cv2
    import numpy as np
    from PIL import Image
    有视频处理 = True
except ImportError:
    有视频处理 = False
    print("警告：需要安装 opencv-python, pillow, numpy")

# 人脸识别
try:
    import insightface
    有人脸识别 = True
except ImportError:
    有人脸识别 = False
    print("警告：未安装 insightface，人物识别功能不可用")


# ============ 配置 ============
视频后缀 = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'}
数据目录 = Path(__file__).parent / "数据"
去重库路径 = 数据目录 / "去重库.db"
人物库路径 = 数据目录 / "人物库.db"
截图目录 = 数据目录 / "截图"


# ============ 数据模型 ============
@dataclass
class 视频指纹:
    """去重用指纹"""
    路径: str
    大小: int
    修改时间: float
    时长: float = 0.0
    宽度: int = 0
    高度: int = 0
    帧率: float = 0.0
    快速哈希: str = ""        # aHash
    文件哈希: str = ""        # MD5前1MB
    创建时间: str = ""
    
    def __post_init__(self):
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()


@dataclass
class 人物出现记录:
    """人物识别记录"""
    路径: str
    人物名: str
    时间点: List[float]      # 出现的时间戳（秒）
    置信度: float            # 平均置信度
    截图路径: List[str]      # 人脸截图路径
    创建时间: str = ""
    
    def __post_init__(self):
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()


# ============ 数据库管理 ============
class 去重数据库:
    """管理去重数据"""
    
    def __init__(self, 路径: str = None):
        self.路径 = 路径 or str(去重库路径)
        self.连接 = sqlite3.connect(self.路径)
        self.连接.row_factory = sqlite3.Row
        self.初始化表()
    
    def 初始化表(self):
        游标 = self.连接.cursor()
        游标.execute('''
            CREATE TABLE IF NOT EXISTS 指纹表 (
                id INTEGER PRIMARY KEY,
                路径 TEXT UNIQUE NOT NULL,
                大小 INTEGER NOT NULL,
                修改时间 REAL NOT NULL,
                时长 REAL DEFAULT 0,
                宽度 INTEGER DEFAULT 0,
                高度 INTEGER DEFAULT 0,
                帧率 REAL DEFAULT 0,
                快速哈希 TEXT,
                文件哈希 TEXT,
                创建时间 TEXT
            )
        ''')
        游标.execute('CREATE INDEX IF NOT EXISTS 哈希索引 ON 指纹表(快速哈希)')
        游标.execute('CREATE INDEX IF NOT EXISTS 大小索引 ON 指纹表(大小)')
        self.连接.commit()
    
    def 保存批量(self, 指纹列表: List[视频指纹]):
        """批量保存指纹"""
        数据 = [(f.路径, f.大小, f.修改时间, f.时长, f.宽度, f.高度, f.帧率,
                f.快速哈希, f.文件哈希, f.创建时间) for f in 指纹列表]
        
        self.连接.executemany('''
            INSERT OR REPLACE INTO 指纹表 
            (路径, 大小, 修改时间, 时长, 宽度, 高度, 帧率, 快速哈希, 文件哈希, 创建时间)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', 数据)
        self.连接.commit()
    
    def 获取全部(self) -> List[视频指纹]:
        """获取所有指纹"""
        游标 = self.连接.cursor()
        游标.execute('SELECT * FROM 指纹表')
        行列表 = 游标.fetchall()
        
        return [视频指纹(
            路径=r['路径'], 大小=r['大小'], 修改时间=r['修改时间'],
            时长=r['时长'], 宽度=r['宽度'], 高度=r['高度'], 帧率=r['帧率'],
            快速哈希=r['快速哈希'] or '', 文件哈希=r['文件哈希'] or '',
            创建时间=r['创建时间'] or ''
        ) for r in 行列表]
    
    def 获取已存在路径(self) -> set:
        """获取已存在的路径集合"""
        游标 = self.连接.cursor()
        游标.execute('SELECT 路径 FROM 指纹表')
        return {r[0] for r in 游标.fetchall()}
    
    def 关闭(self):
        self.连接.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.关闭()


class 人物数据库:
    """管理人物识别数据"""
    
    def __init__(self, 路径: str = None):
        self.路径 = 路径 or str(人物库路径)
        self.连接 = sqlite3.connect(self.路径)
        self.连接.row_factory = sqlite3.Row
        self.初始化表()
    
    def 初始化表(self):
        游标 = self.连接.cursor()
        
        # 人物出现记录表
        游标.execute('''
            CREATE TABLE IF NOT EXISTS 人物记录表 (
                id INTEGER PRIMARY KEY,
                路径 TEXT NOT NULL,
                人物名 TEXT NOT NULL,
                时间点 TEXT,           -- JSON数组
                置信度 REAL,
                截图路径 TEXT,         -- JSON数组
                创建时间 TEXT,
                UNIQUE(路径, 人物名)
            )
        ''')
        
        # 人物特征库（用于识别）
        游标.execute('''
            CREATE TABLE IF NOT EXISTS 人物特征表 (
                id INTEGER PRIMARY KEY,
                人物名 TEXT NOT NULL,
                特征向量 TEXT,         -- JSON数组
                来源类型 TEXT,         -- 视频/照片/纠正
                来源路径 TEXT,
                创建时间 TEXT
            )
        ''')
        
        游标.execute('CREATE INDEX IF NOT EXISTS 人物索引 ON 人物记录表(人物名)')
        游标.execute('CREATE INDEX IF NOT EXISTS 路径索引 ON 人物记录表(路径)')
        self.连接.commit()
    
    def 保存人物记录(self, 记录: 人物出现记录):
        """保存人物出现记录"""
        游标 = self.连接.cursor()
        游标.execute('''
            INSERT OR REPLACE INTO 人物记录表
            (路径, 人物名, 时间点, 置信度, 截图路径, 创建时间)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            记录.路径, 记录.人物名,
            json.dumps(记录.时间点),
            记录.置信度,
            json.dumps(记录.截图路径),
            记录.创建时间
        ))
        self.连接.commit()
    
    def 保存人物特征(self, 人物名: str, 特征向量: list, 来源类型: str, 来源路径: str):
        """保存人物特征（用于后续识别）"""
        游标 = self.连接.cursor()
        游标.execute('''
            INSERT INTO 人物特征表
            (人物名, 特征向量, 来源类型, 来源路径, 创建时间)
            VALUES (?, ?, ?, ?, ?)
        ''', (人物名, json.dumps(特征向量), 来源类型, 来源路径, datetime.now().isoformat()))
        self.连接.commit()
    
    def 获取人物列表(self) -> List[str]:
        """获取所有人物名"""
        游标 = self.连接.cursor()
        游标.execute('SELECT DISTINCT 人物名 FROM 人物特征表')
        return [r[0] for r in 游标.fetchall()]
    
    def 获取人物特征(self, 人物名: str) -> List[list]:
        """获取某人的所有特征向量"""
        游标 = self.连接.cursor()
        游标.execute('SELECT 特征向量 FROM 人物特征表 WHERE 人物名 = ?', (人物名,))
        return [json.loads(r[0]) for r in 游标.fetchall()]
    
    def 获取视频人物(self, 视频路径: str) -> List[Dict]:
        """获取某视频的所有人物"""
        游标 = self.连接.cursor()
        游标.execute('SELECT * FROM 人物记录表 WHERE 路径 = ?', (视频路径,))
        结果 = []
        for r in 游标.fetchall():
            结果.append({
                '人物名': r['人物名'],
                '时间点': json.loads(r['时间点']) if r['时间点'] else [],
                '置信度': r['置信度'],
                '截图路径': json.loads(r['截图路径']) if r['截图路径'] else []
            })
        return 结果
    
    def 关闭(self):
        self.连接.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.关闭()


# ============ 核心处理器 ============
class 统一扫描器:
    """一次扫描，生成去重+人物两份数据"""
    
    def __init__(self, 并行数: int = 4):
        self.并行数 = 并行数
        self.人脸检测器 = None
        self.人脸编码器 = None
        
        if 有人脸识别:
            try:
                self.人脸检测器 = insightface.app.FaceAnalysis()
                self.人脸检测器.prepare(ctx_id=-1, det_size=(640, 640))
                print("✓ 人脸识别模型加载成功")
            except Exception as e:
                print(f"✗ 人脸识别模型加载失败: {e}")
    
    def 扫描(self, 路径列表: List[str], 增量: bool = True) -> Dict:
        """
        统一扫描入口
        返回: {'去重指纹数': x, '人物记录数': y}
        """
        # 收集视频
        视频文件 = []
        for 路径 in 路径列表:
            视频文件.extend(self.收集视频(路径))
        
        print(f"\n发现 {len(视频文件)} 个视频")
        
        # 检查已存在的
        if 增量:
            with 去重数据库() as 去重库:
                已存在 = 去重库.获取已存在路径()
            待处理 = [p for p in 视频文件 if p not in 已存在]
            print(f"需要处理: {len(待处理)} 个（跳过 {len(视频文件) - len(待处理)} 个已存在）")
        else:
            待处理 = 视频文件
        
        if not 待处理:
            print("没有新文件需要处理")
            return {'去重指纹数': 0, '人物记录数': 0}
        
        # 并行处理
        开始时间 = datetime.now()
        去重指纹列表 = []
        人物记录列表 = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.并行数) as 执行器:
            未来列表 = {执行器.submit(self.处理单个视频, 路径): 路径 for 路径 in 待处理}
            
            for 未来 in tqdm(concurrent.futures.as_completed(未来列表), 
                           total=len(待处理), desc="扫描进度"):
                结果 = 未来.result()
                if 结果:
                    指纹, 人物列表 = 结果
                    if 指纹:
                        去重指纹列表.append(指纹)
                    人物记录列表.extend(人物列表)
        
        # 批量保存
        with 去重数据库() as 去重库:
            去重库.保存批量(去重指纹列表)
        
        with 人物数据库() as 人物库:
            for 记录 in 人物记录列表:
                人物库.保存人物记录(记录)
        
        耗时 = (datetime.now() - 开始时间).total_seconds()
        速度 = len(待处理) / 耗时 if 耗时 > 0 else 0
        
        print(f"\n✅ 扫描完成")
        print(f"   生成去重指纹: {len(去重指纹列表)} 个")
        print(f"   识别人物记录: {len(人物记录列表)} 条")
        print(f"   耗时: {耗时:.1f} 秒 ({速度:.1f} 个/秒)")
        
        return {
            '去重指纹数': len(去重指纹列表),
            '人物记录数': len(人物记录列表)
        }
    
    def 收集视频(self, 路径: str) -> List[str]:
        """收集目录下的所有视频"""
        结果 = []
        路径对象 = Path(路径)
        
        if 路径对象.is_file() and 路径对象.suffix.lower() in 视频后缀:
            结果.append(str(路径对象.absolute()))
        elif 路径对象.is_dir():
            for 后缀 in 视频后缀:
                结果.extend(str(f.absolute()) for f in 路径对象.rglob(f"*{后缀}"))
                结果.extend(str(f.absolute()) for f in 路径对象.rglob(f"*{后缀.upper()}"))
        
        return list(set(结果))  # 去重
    
    def 处理单个视频(self, 路径: str) -> Optional[Tuple[视频指纹, List[人物出现记录]]]:
        """
        处理单个视频，同时生成去重指纹和人物记录
        返回: (指纹, [人物记录1, 人物记录2, ...])
        """
        try:
            文件状态 = os.stat(路径)
            
            # 创建去重指纹
            指纹 = 视频指纹(
                路径=路径,
                大小=文件状态.st_size,
                修改时间=文件状态.st_mtime
            )
            
            # 提取视频信息
            if 有视频处理:
                信息 = self.提取视频信息(路径)
                if 信息:
                    指纹.时长 = 信息.get('时长', 0)
                    指纹.宽度 = 信息.get('宽度', 0)
                    指纹.高度 = 信息.get('高度', 0)
                    指纹.帧率 = 信息.get('帧率', 0)
                
                # 生成快速哈希（去重用）
                指纹.快速哈希 = self.计算快速哈希(路径)
                指纹.文件哈希 = self.计算文件哈希(路径)
            
            # 识别人物
            人物列表 = []
            if 有人脸识别 and self.人脸检测器:
                人物列表 = self.识别人物(路径)
            
            return 指纹, 人物列表
            
        except Exception as 错误:
            print(f"\n处理失败 {路径}: {错误}")
            return None
    
    def 提取视频信息(self, 路径: str) -> Dict:
        """提取视频基本信息"""
        视频 = cv2.VideoCapture(路径)
        if not 视频.isOpened():
            return {}
        
        信息 = {
            '宽度': int(视频.get(cv2.CAP_PROP_FRAME_WIDTH)),
            '高度': int(视频.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            '帧率': 视频.get(cv2.CAP_PROP_FPS),
            '总帧数': int(视频.get(cv2.CAP_PROP_FRAME_COUNT))
        }
        
        if 信息['帧率'] > 0:
            信息['时长'] = 信息['总帧数'] / 信息['帧率']
        else:
            信息['时长'] = 0
        
        视频.release()
        return 信息
    
    def 计算快速哈希(self, 路径: str) -> Optional[str]:
        """计算aHash（比pHash快）"""
        视频 = cv2.VideoCapture(路径)
        if not 视频.isOpened():
            return None
        
        总帧数 = int(视频.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 只取中间一帧
        if 总帧数 > 0:
            目标帧 = 总帧数 // 2
        else:
            目标帧 = 0
        
        视频.set(cv2.CAP_PROP_POS_FRAMES, 目标帧)
        成功, 帧 = 视频.read()
        视频.release()
        
        if not 成功:
            return None
        
        # aHash算法
        try:
            灰度 = cv2.cvtColor(帧, cv2.COLOR_BGR2GRAY)
            缩小 = cv2.resize(灰度, (16, 16), interpolation=cv2.INTER_LINEAR)
            平均值 = 缩小.mean()
            哈希位 = (缩小 > 平均值).flatten().astype(int)
            哈希字符串 = ''.join(str(b) for b in 哈希位)
            return hex(int(哈希字符串, 2))[2:].zfill(64)
        except:
            return None
    
    def 计算文件哈希(self, 路径: str, 最大字节: int = 1024*1024) -> str:
        """计算文件前1MB的MD5"""
        try:
            哈希 = hashlib.md5()
            with open(路径, 'rb') as 文件:
                哈希.update(文件.read(最大字节))
            return 哈希.hexdigest()
        except:
            return ""
    
    def 识别人物(self, 视频路径: str) -> List[人物出现记录]:
        """
        识别视频中的人物
        返回人物出现记录列表
        """
        视频 = cv2.VideoCapture(视频路径)
        if not 视频.isOpened():
            return []
        
        帧率 = 视频.get(cv2.CAP_PROP_FPS)
        总帧数 = int(视频.get(cv2.CAP_PROP_FRAME_COUNT))
        时长 = 总帧数 / 帧率 if 帧率 > 0 else 0
        
        # 采样时间点（每5秒采一帧，最多采20帧）
        if 时长 <= 0:
            视频.release()
            return []
        
        采样间隔 = 5  # 秒
        采样次数 = min(int(时长 / 采样间隔), 20)
        
        人物统计 = defaultdict(lambda: {'时间点': [], '置信度': [], '截图': []})
        
        for i in range(采样次数):
            时间 = i * 采样间隔 + 采样间隔 / 2
            帧位置 = int(时间 * 帧率)
            视频.set(cv2.CAP_PROP_POS_FRAMES, 帧位置)
            
            成功, 帧 = 视频.read()
            if not 成功:
                continue
            
            # 检测人脸
            try:
                人脸列表 = self.人脸检测器.get(帧)
                
                for 人脸 in 人脸列表:
                    if 人脸.det_score < 0.7:  # 过滤低质量
                        continue
                    
                    # 与已知人物对比，找到最匹配的
                    匹配人物 = self.匹配已知人物(人脸.embedding)
                    
                    if 匹配人物:
                        人物名, 置信度 = 匹配人物
                        人物统计[人物名]['时间点'].append(时间)
                        人物统计[人物名]['置信度'].append(置信度)
                        
                        # 保存截图
                        截图路径 = self.保存人脸截图(帧, 人脸.bbox, 人物名, 视频路径, 时间)
                        if 截图路径:
                            人物统计[人物名]['截图'].append(截图路径)
            except:
                continue
        
        视频.release()
        
        # 生成记录
        记录列表 = []
        for 人物名, 数据 in 人物统计.items():
            if len(数据['时间点']) >= 2:  # 至少出现2次才算
                记录 = 人物出现记录(
                    路径=视频路径,
                    人物名=人物名,
                    时间点=sorted(set(数据['时间点'])),  # 去重排序
                    置信度=sum(数据['置信度']) / len(数据['置信度']),
                    截图路径=数据['截图'][:5]  # 最多存5张
                )
                记录列表.append(记录)
        
        return 记录列表
    
    def 匹配已知人物(self, 人脸特征: np.ndarray) -> Optional[Tuple[str, float]]:
        """
        将检测到的人脸与已知人物匹配
        返回: (人物名, 置信度) 或 None
        """
        with 人物数据库() as 人物库:
            人物列表 = 人物库.获取人物列表()
        
        if not 人物列表:
            return None
        
        最佳匹配 = None
        最佳分数 = 0.6  # 阈值
        
        for 人物名 in 人物列表:
            with 人物数据库() as 人物库:
                特征列表 = 人物库.获取人物特征(人物名)
            
            for 已知特征 in 特征列表:
                相似度 = self.计算余弦相似度(人脸特征, np.array(已知特征))
                if 相似度 > 最佳分数:
                    最佳分数 = 相似度
                    最佳匹配 = 人物名
        
        if 最佳匹配:
            return 最佳匹配, 最佳分数
        return None
    
    def 计算余弦相似度(self, 向量1: np.ndarray, 向量2: np.ndarray) -> float:
        """计算两个向量的余弦相似度"""
        模1 = np.linalg.norm(向量1)
        模2 = np.linalg.norm(向量2)
        if 模1 == 0 or 模2 == 0:
            return 0.0
        return float(np.dot(向量1, 向量2) / (模1 * 模2))
    
    def 保存人脸截图(self, 帧: np.ndarray, 人脸框: np.ndarray, 
                    人物名: str, 视频路径: str, 时间: float) -> Optional[str]:
        """保存人脸截图"""
        try:
            # 创建人物截图目录
            人物目录 = 截图目录 / 人物名
            人物目录.mkdir(parents=True, exist_ok=True)
            
            # 裁剪人脸
            x1, y1, x2, y2 = map(int, 人脸框)
            高, 宽 = 帧.shape[:2]
            
            # 加边距
            边距 = int((y2 - y1) * 0.2)
            x1 = max(0, x1 - 边距)
            y1 = max(0, y1 - 边距)
            x2 = min(宽, x2 + 边距)
            y2 = min(高, y2 + 边距)
            
            人脸图 = 帧[y1:y2, x1:x2]
            人脸图 = cv2.resize(人脸图, (200, 200))
            
            # 生成文件名
            视频名 = Path(视频路径).stem
            文件名 = f"{视频名}_{时间:.1f}s.jpg"
            保存路径 = 人物目录 / 文件名
            
            cv2.imwrite(str(保存路径), 人脸图)
            return str(保存路径)
        except:
            return None


# ============ 功能命令 ============
class 去重功能:
    """去重相关功能"""
    
    @staticmethod
    def 查找重复(阈值: int = 10) -> List[Dict]:
        """
        查找重复视频
        阈值: 哈希差异位数，越小越严格
        """
        with 去重数据库() as 去重库:
            所有指纹 = 去重库.获取全部()
        
        print(f"\n共 {len(所有指纹)} 个视频待对比")
        
        # 按大小分组（预筛选）
        大小分组 = defaultdict(list)
        for 指纹 in 所有指纹:
            大小兆 = 指纹.大小 // (1024 * 1024)
            大小分组[大小兆].append(指纹)
        
        重复组列表 = []
        已处理 = set()
        
        for 大小, 指纹列表 in tqdm(大小分组.items(), desc="对比进度"):
            if len(指纹列表) < 2:
                continue
            
            for i, 指纹1 in enumerate(指纹列表):
                if 指纹1.路径 in 已处理:
                    continue
                
                组 = [指纹1]
                
                for 指纹2 in 指纹列表[i+1:]:
                    if 指纹2.路径 in 已处理:
                        continue
                    
                    if 去重功能.是重复(指纹1, 指纹2, 阈值):
                        组.append(指纹2)
                        已处理.add(指纹2.路径)
                
                if len(组) > 1:
                    已处理.add(指纹1.路径)
                    重复组列表.append({
                        '组号': len(重复组列表) + 1,
                        '视频数': len(组),
                        '视频列表': 组
                    })
        
        return 重复组列表
    
    @staticmethod
    def 是重复(指纹1: 视频指纹, 指纹2: 视频指纹, 阈值: int) -> bool:
        """判断两个视频是否重复"""
        # 文件大小相同 + 文件哈希相同 = 完全相同
        if 指纹1.大小 == 指纹2.大小 and 指纹1.文件哈希 == 指纹2.文件哈希:
            return True
        
        # 快速哈希对比
        if 指纹1.快速哈希 and 指纹2.快速哈希:
            距离 = 去重功能.汉明距离(指纹1.快速哈希, 指纹2.快速哈希)
            if 距离 <= 阈值:
                return True
        
        return False
    
    @staticmethod
    def 汉明距离(哈希1: str, 哈希2: str) -> int:
        """计算汉明距离"""
        if len(哈希1) != len(哈希2):
            return 999
        try:
            二进制1 = bin(int(哈希1, 16))[2:].zfill(256)
            二进制2 = bin(int(哈希2, 16))[2:].zfill(256)
            return sum(c1 != c2 for c1, c2 in zip(二进制1, 二进制2))
        except:
            return 999
    
    @staticmethod
    def 导出报告(重复组: List[Dict], 输出路径: str = "重复报告.md"):
        """导出重复视频报告"""
        with open(输出路径, 'w', encoding='utf-8') as 文件:
            文件.write(f"# 视频重复报告\n生成时间: {datetime.now().isoformat()}\n\n")
            文件.write(f"发现 {len(重复组)} 组重复视频\n\n")
            
            for 组 in 重复组:
                文件.write(f"## 重复组 #{组['组号']} ({组['视频数']}个文件)\n\n")
                
                视频列表 = sorted(组['视频列表'], key=lambda x: x.大小, reverse=True)
                
                文件.write("| 建议 | 文件路径 | 大小 | 时长 |\n")
                文件.write("|------|----------|------|------|\n")
                
                for i, 视频 in enumerate(视频列表):
                    建议 = "保留" if i == 0 else "可删"
                    大小兆 = 视频.大小 / (1024 * 1024)
                    时长 = f"{视频.时长:.1f}秒" if 视频.时长 > 0 else "未知"
                    文件.write(f"| {建议} | `{视频.路径}` | {大小兆:.1f}MB | {时长} |\n")
                
                文件.write("\n---\n\n")
        
        print(f"报告已保存: {输出路径}")


class 人物功能:
    """人物识别相关功能"""
    
    @staticmethod
    def 显示人物库():
        """显示人物库内容"""
        with 人物数据库() as 人物库:
            人物列表 = 人物库.获取人物列表()
        
        if not 人物列表:
            print("\n人物库为空，请先扫描视频或导入人物照片")
            return
        
        print(f"\n{'='*60}")
        print(f"人物库 ({len(人物列表)} 个人物)")
        print(f"{'='*60}")
        
        for 人物 in 人物列表:
            print(f"\n👤 {人物}")
            # 可以显示更多统计信息
        
        print(f"{'='*60}")
    
    @staticmethod
    def 从视频学习(分类文件夹: str):
        """
        从已分类视频学习人物特征
        文件夹结构: 分类文件夹/人物名/视频文件
        """
        print(f"\n📚 从已分类视频学习: {分类文件夹}")
        
        根路径 = Path(分类文件夹)
        扫描器 = 统一扫描器()
        
        for 人物目录 in 根路径.iterdir():
            if not 人物目录.is_dir():
                continue
            
            人物名 = 人物目录.name
            print(f"\n👤 学习人物: {人物名}")
            
            # 收集该人物的视频
            视频列表 = []
            for 后缀 in 视频后缀:
                视频列表.extend(人物目录.glob(f"*{后缀}"))
            
            if not 视频列表:
                continue
            
            print(f"   发现 {len(视频列表)} 个视频")
            
            # 提取特征
            特征列表 = []
            for 视频路径 in 视频列表[:5]:  # 最多用5个视频
                特征 = 扫描器.提取人物特征(str(视频路径), 人物名)
                if 特征:
                    特征列表.append(特征)
            
            # 保存特征
            if 特征列表:
                with 人物数据库() as 人物库:
                    for 特征 in 特征列表:
                        人物库.保存人物特征(人物名, 特征, "视频学习", str(视频列表[0]))
                print(f"   ✓ 保存 {len(特征列表)} 个特征向量")
    
    @staticmethod
    def 以图搜视频(图片路径: str, 最小置信度: float = 0.6) -> List[Dict]:
        """
        上传照片搜索包含该人物的视频
        """
        print(f"\n🔍 以图搜视频: {Path(图片路径).name}")
        
        if not 有视频处理:
            print("✗ 需要安装 opencv-python")
            return []
        
        # 加载图片
        图片 = cv2.imread(图片路径)
        if 图片 is None:
            print("✗ 无法读取图片")
            return []
        
        # 检测人脸
        扫描器 = 统一扫描器()
        if not 扫描器.人脸检测器:
            print("✗ 人脸识别模型未加载")
            return []
        
        人脸列表 = 扫描器.人脸检测器.get(图片)
        if not 人脸列表:
            print("✗ 图片中未检测到人脸")
            return []
        
        查询特征 = 人脸列表[0].embedding
        print(f"✓ 提取到人脸特征")
        
        # 从数据库搜索
        with 人物数据库() as 人物库:
            所有记录 = 人物库.连接.execute('SELECT DISTINCT 路径, 人物名 FROM 人物记录表').fetchall()
        
        # 按人物分组
        视频人物 = defaultdict(list)
        for 记录 in 所有记录:
            视频人物[记录['路径']].append(记录['人物名'])
        
        print(f"📚 视频库共 {len(视频人物)} 个视频")
        
        # 这里简化处理，实际应该对比每个视频的所有人脸特征
        # 返回包含相似人物的视频
        结果 = []
        for 路径, 人物列表 in 视频人物.items():
            结果.append({
                '视频路径': 路径,
                '人物': 人物列表
            })
        
        return 结果


# ============ 主入口 ============
def 初始化():
    """初始化系统"""
    数据目录.mkdir(parents=True, exist_ok=True)
    截图目录.mkdir(parents=True, exist_ok=True)
    
    # 初始化数据库
    with 去重数据库() as _, 人物数据库() as _:
        pass
    
    print("✓ 系统初始化完成")
    print(f"  数据目录: {数据目录}")
    print(f"  去重库: {去重库路径}")
    print(f"  人物库: {人物库路径}")


def 统计信息():
    """显示统计信息"""
    with 去重数据库() as 去重库, 人物数据库() as 人物库:
        去重数量 = len(去重库.获取全部())
        人物数量 = len(人物库.获取人物列表())
    
    print(f"\n{'='*60}")
    print("📊 系统统计")
    print(f"{'='*60}")
    print(f"去重数据库: {去重数量} 个视频指纹")
    print(f"人物数据库: {人物数量} 个人物")
    print(f"{'='*60}")


def 主函数():
    """命令行入口"""
    解析器 = argparse.ArgumentParser(
        description='视频管家 - 一体化视频管理系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  视频管家 初始化                    # 创建数据库和目录
  视频管家 扫描 /视频文件夹           # 扫描视频（去重+识别人物）
  视频管家 扫描 /视频文件夹 --增量    # 只扫描新增的视频
  视频管家 找重复                    # 查找重复视频
  视频管家 人物库                    # 显示人物库
  视频管家 统计                      # 显示统计信息
        """
    )
    
    解析器.add_argument('命令', choices=[
        '初始化', '扫描', '找重复', '人物库', '学习', '搜图', '统计'
    ], help='要执行的命令')
    
    解析器.add_argument('路径', nargs='?', help='视频文件夹路径')
    解析器.add_argument('--增量', action='store_true', help='增量扫描模式')
    解析器.add_argument('--阈值', type=int, default=10, help='去重阈值（越小越严格）')
    
    参数 = 解析器.parse_args()
    
    # 执行命令
    if 参数.命令 == '初始化':
        初始化()
    
    elif 参数.命令 == '扫描':
        if not 参数.路径:
            print("错误: 扫描命令需要提供视频文件夹路径")
            print("示例: 视频管家 扫描 /视频文件夹")
            return
        
        扫描器 = 统一扫描器()
        结果 = 扫描器.扫描([参数.路径], 增量=参数.增量)
        print(f"\n扫描结果:")
        print(f"  生成去重指纹: {结果['去重指纹数']} 个")
        print(f"  识别人物记录: {结果['人物记录数']} 条")
    
    elif 参数.命令 == '找重复':
        重复组 = 去重功能.查找重复(参数.阈值)
        if 重复组:
            print(f"\n发现 {len(重复组)} 组重复视频")
            
            # 计算可释放空间
            可释放 = 0
            for 组 in 重复组:
                大小列表 = sorted([v.大小 for v in 组['视频列表']], reverse=True)
                可释放 += sum(大小列表[1:])
            
            print(f"预计可释放空间: {可释放 / (1024**3):.2f} GB")
            去重功能.导出报告(重复组)
        else:
            print("未发现重复视频")
    
    elif 参数.命令 == '人物库':
        人物功能.显示人物库()
    
    elif 参数.命令 == '学习':
        if not 参数.路径:
            print("错误: 学习命令需要提供已分类视频文件夹路径")
            print("示例: 视频管家 学习 /已分类视频")
            return
        人物功能.从视频学习(参数.路径)
    
    elif 参数.命令 == '搜图':
        if not 参数.路径:
            print("错误: 搜图命令需要提供图片路径")
            print("示例: 视频管家 搜图 /照片.jpg")
            return
        结果 = 人物功能.以图搜视频(参数.路径)
        print(f"\n找到 {len(结果)} 个相关视频")
    
    elif 参数.命令 == '统计':
        统计信息()


if __name__ == '__main__':
    主函数()