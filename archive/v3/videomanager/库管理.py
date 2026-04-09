#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
库管理模块 - 视频库标记与分类管理
功能：
  - 库标记（未分类/分类中/已分类）
  - 人物关联标记
  - 智能分类检测
  - 库统计与可视化
"""
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import re

# 数据目录
数据目录 = Path(__file__).parent / "数据"
库管理数据库路径 = 数据目录 / "库管理.db"

# 视频后缀
视频后缀 = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'}


@dataclass
class 视频库:
    """视频库模型"""
    路径: str
    名称: str = ""
    分类状态: str = "未分类"  # 未分类 / 分类中 / 已分类
    关联人物: List[str] = None
    视频数量: int = 0
    总大小: int = 0
    总时长: float = 0.0
    最后扫描时间: str = ""
    创建时间: str = ""
    备注: str = ""
    
    def __post_init__(self):
        if not self.名称:
            self.名称 = Path(self.路径).name
        if self.关联人物 is None:
            self.关联人物 = []
        if not self.创建时间:
            self.创建时间 = datetime.now().isoformat()


class 库管理数据库:
    """库管理数据库操作"""
    
    def __init__(self, 路径: str = None):
        self.路径 = 路径 or str(库管理数据库路径)
        self.连接 = sqlite3.connect(self.路径)
        self.连接.row_factory = sqlite3.Row
        self.初始化表()
    
    def 初始化表(self):
        """初始化数据库表结构"""
        游标 = self.连接.cursor()
        
        # 主库表
        游标.execute('''
            CREATE TABLE IF NOT EXISTS 视频库表 (
                id INTEGER PRIMARY KEY,
                路径 TEXT UNIQUE NOT NULL,
                名称 TEXT,
                分类状态 TEXT DEFAULT '未分类',
                关联人物 TEXT,           -- JSON数组
                视频数量 INTEGER DEFAULT 0,
                总大小 INTEGER DEFAULT 0,
                总时长 REAL DEFAULT 0,
                最后扫描时间 TEXT,
                创建时间 TEXT,
                备注 TEXT
            )
        ''')
        
        # 库与去重库的关联表
        游标.execute('''
            CREATE TABLE IF NOT EXISTS 库视频关联表 (
                id INTEGER PRIMARY KEY,
                库路径 TEXT NOT NULL,
                视频路径 TEXT NOT NULL,
                UNIQUE(库路径, 视频路径)
            )
        ''')
        
        游标.execute('CREATE INDEX IF NOT EXISTS 库路径索引 ON 视频库表(路径)')
        游标.execute('CREATE INDEX IF NOT EXISTS 状态索引 ON 视频库表(分类状态)')
        self.连接.commit()
    
    def 添加库(self, 库: 视频库) -> bool:
        """添加或更新视频库"""
        try:
            游标 = self.连接.cursor()
            游标.execute('''
                INSERT OR REPLACE INTO 视频库表
                (路径, 名称, 分类状态, 关联人物, 视频数量, 总大小, 总时长, 
                 最后扫描时间, 创建时间, 备注)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                库.路径, 库.名称, 库.分类状态, json.dumps(库.关联人物),
                库.视频数量, 库.总大小, 库.总时长,
                库.最后扫描时间, 库.创建时间, 库.备注
            ))
            self.连接.commit()
            return True
        except Exception as e:
            print(f"添加库失败: {e}")
            return False
    
    def 获取库(self, 路径: str) -> Optional[视频库]:
        """获取单个库信息"""
        游标 = self.连接.cursor()
        游标.execute('SELECT * FROM 视频库表 WHERE 路径 = ?', (路径,))
        行 = 游标.fetchone()
        if not 行:
            return None
        return self._行转库(行)
    
    def 获取所有库(self) -> List[视频库]:
        """获取所有库列表"""
        游标 = self.连接.cursor()
        游标.execute('SELECT * FROM 视频库表 ORDER BY 创建时间 DESC')
        return [self._行转库(行) for 行 in 游标.fetchall()]
    
    def 按状态获取库(self, 状态: str) -> List[视频库]:
        """按分类状态获取库"""
        游标 = self.连接.cursor()
        游标.execute('SELECT * FROM 视频库表 WHERE 分类状态 = ?', (状态,))
        return [self._行转库(行) for 行 in 游标.fetchall()]
    
    def 更新库状态(self, 路径: str, 状态: str) -> bool:
        """更新库的分类状态"""
        try:
            游标 = self.连接.cursor()
            游标.execute('''
                UPDATE 视频库表 SET 分类状态 = ?, 最后扫描时间 = ?
                WHERE 路径 = ?
            ''', (状态, datetime.now().isoformat(), 路径))
            self.连接.commit()
            return True
        except Exception as e:
            print(f"更新状态失败: {e}")
            return False
    
    def 更新库人物(self, 路径: str, 人物列表: List[str]) -> bool:
        """更新库的关联人物"""
        try:
            游标 = self.连接.cursor()
            游标.execute('''
                UPDATE 视频库表 SET 关联人物 = ?, 最后扫描时间 = ?
                WHERE 路径 = ?
            ''', (json.dumps(人物列表), datetime.now().isoformat(), 路径))
            self.连接.commit()
            return True
        except Exception as e:
            print(f"更新人物失败: {e}")
            return False
    
    def 更新库统计(self, 路径: str, 视频数: int, 总大小: int, 总时长: float) -> bool:
        """更新库的统计数据"""
        try:
            游标 = self.连接.cursor()
            游标.execute('''
                UPDATE 视频库表 SET 
                    视频数量 = ?, 总大小 = ?, 总时长 = ?, 最后扫描时间 = ?
                WHERE 路径 = ?
            ''', (视频数, 总大小, 总时长, datetime.now().isoformat(), 路径))
            self.连接.commit()
            return True
        except Exception as e:
            print(f"更新统计失败: {e}")
            return False
    
    def 删除库(self, 路径: str) -> bool:
        """删除库记录"""
        try:
            游标 = self.连接.cursor()
            游标.execute('DELETE FROM 视频库表 WHERE 路径 = ?', (路径,))
            游标.execute('DELETE FROM 库视频关联表 WHERE 库路径 = ?', (路径,))
            self.连接.commit()
            return True
        except Exception as e:
            print(f"删除库失败: {e}")
            return False
    
    def 获取统计概览(self) -> Dict:
        """获取统计概览"""
        游标 = self.连接.cursor()
        
        # 总数统计
        游标.execute('''
            SELECT 
                COUNT(*) as 总数,
                SUM(CASE WHEN 分类状态 = '未分类' THEN 1 ELSE 0 END) as 未分类数,
                SUM(CASE WHEN 分类状态 = '分类中' THEN 1 ELSE 0 END) as 分类中数,
                SUM(CASE WHEN 分类状态 = '已分类' THEN 1 ELSE 0 END) as 已分类数,
                SUM(视频数量) as 总视频数,
                SUM(总大小) as 总大小,
                SUM(总时长) as 总时长
            FROM 视频库表
        ''')
        行 = 游标.fetchone()
        
        return {
            '库总数': 行['总数'] or 0,
            '未分类': 行['未分类数'] or 0,
            '分类中': 行['分类中数'] or 0,
            '已分类': 行['已分类数'] or 0,
            '总视频数': 行['总视频数'] or 0,
            '总大小GB': (行['总大小'] or 0) / (1024**3),
            '总时长小时': (行['总时长'] or 0) / 3600
        }
    
    def _行转库(self, 行) -> 视频库:
        """数据库行转视频库对象"""
        return 视频库(
            路径=行['路径'],
            名称=行['名称'],
            分类状态=行['分类状态'],
            关联人物=json.loads(行['关联人物']) if 行['关联人物'] else [],
            视频数量=行['视频数量'],
            总大小=row['总大小'],
            总时长=row['总时长'],
            最后扫描时间=row['最后扫描时间'] or '',
            创建时间=row['创建时间'] or '',
            备注=row['备注'] or ''
        )
    
    def 关闭(self):
        self.连接.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.关闭()


class 智能分类检测器:
    """智能检测文件夹的分类状态"""
    
    # 常见非人物文件夹名称
    系统文件夹 = {'新建文件夹', 'temp', 'tmp', 'cache', 'backup', '回收站'}
    
    # 可能的分类文件夹特征
    分类特征 = {
        '按人分类': r'^[\u4e00-\u9fa5]{2,8}$|^\w{2,20}$',  # 2-8个汉字或2-20个字符
        '按日期分类': r'^\d{4}[-/年]?\d{2}[-/月]?\d{0,2}',
        '按类型分类': r'电影|电视剧|综艺|动画|纪录片|MV|短片|合集',
        '按来源分类': r'下载|录制|转码|剪辑|备份'
    }
    
    @classmethod
    def 分析文件夹结构(cls, 路径: str) -> Dict:
        """
        分析文件夹结构，判断分类方式
        返回: {
            '分类类型': str,
            '置信度': float,
            '检测到的分类': List[str],
            '视频分布': Dict,
            '建议': str
        }
        """
        根路径 = Path(路径)
        if not 根路径.exists():
            return {'错误': '路径不存在'}
        
        结果 = {
            '分类类型': '未知',
            '置信度': 0.0,
            '检测到的分类': [],
            '视频分布': {},
            '建议': ''
        }
        
        # 获取子文件夹
        子文件夹 = [d for d in 根路径.iterdir() if d.is_dir()]
        
        if not 子文件夹:
            # 没有子文件夹，可能是扁平结构
            视频列表 = cls._收集视频(路径)
            结果['视频分布']['根目录'] = len(视频列表)
            if len(视频列表) > 0:
                结果['分类类型'] = '扁平结构'
                结果['置信度'] = 0.5
                结果['建议'] = '建议按人物或类型创建子文件夹进行分类'
            return 结果
        
        # 分析每个子文件夹
        分类统计 = defaultdict(int)
        人物候选 = []
        
        for 子文件夹路径 in 子文件夹:
            文件夹名 = 子文件夹路径.name
            
            # 跳过系统文件夹
            if 文件夹名 in cls.系统文件夹:
                continue
            
            # 统计视频数量
            视频数 = len(cls._收集视频(str(子文件夹路径)))
            if 视频数 == 0:
                continue
            
            结果['视频分布'][文件夹名] = 视频数
            
            # 检测分类类型
            if re.match(cls.分类特征['按人分类'], 文件夹名):
                分类统计['按人分类'] += 1
                人物候选.append(文件夹名)
            elif re.search(cls.分类特征['按类型分类'], 文件夹名):
                分类统计['按类型分类'] += 1
            elif re.match(cls.分类特征['按日期分类'], 文件夹名):
                分类统计['按日期分类'] += 1
            else:
                分类统计['其他'] += 1
        
        # 判断主分类类型
        if 分类统计['按人分类'] >= len(子文件夹) * 0.6:
            结果['分类类型'] = '按人分类'
            结果['置信度'] = 分类统计['按人分类'] / len(子文件夹)
            结果['检测到的分类'] = 人物候选
            结果['建议'] = '这是一个按人物分类的库，可以进行人脸识别学习'
        elif 分类统计['按类型分类'] >= len(子文件夹) * 0.4:
            结果['分类类型'] = '按类型分类'
            结果['置信度'] = 分类统计['按类型分类'] / len(子文件夹)
            结果['建议'] = '这是一个按类型分类的库'
        elif 分类统计['按日期分类'] >= len(子文件夹) * 0.4:
            结果['分类类型'] = '按日期分类'
            结果['置信度'] = 分类统计['按日期分类'] / len(子文件夹)
            结果['建议'] = '这是一个按日期分类的库'
        else:
            结果['分类类型'] = '混合/未分类'
            结果['置信度'] = 0.3
            结果['建议'] = '分类结构不清晰，建议重新整理'
        
        return 结果
    
    @classmethod
    def 检测并标记库(cls, 路径: str, 自动标记: bool = True) -> Dict:
        """
        检测文件夹并自动标记库
        """
        分析结果 = cls.分析文件夹结构(路径)
        
        if '错误' in 分析结果:
            return 分析结果
        
        # 计算视频统计
        总视频 = sum(分析结果['视频分布'].values())
        总大小 = cls._计算总大小(路径)
        
        # 确定分类状态
        if 分析结果['分类类型'] == '按人分类' and 分析结果['置信度'] > 0.7:
            状态 = '已分类'
        elif 分析结果['置信度'] > 0.5:
            状态 = '分类中'
        else:
            状态 = '未分类'
        
        # 创建库对象
        库 = 视频库(
            路径=路径,
            名称=Path(路径).name,
            分类状态=状态,
            关联人物=分析结果['检测到的分类'] if 分析结果['分类类型'] == '按人分类' else [],
            视频数量=总视频,
            总大小=总大小,
            备注=f"自动检测: {分析结果['分类类型']} (置信度{分析结果['置信度']:.0%})"
        )
        
        # 保存到数据库
        if 自动标记:
            with 库管理数据库() as db:
                db.添加库(库)
        
        return {
            '库信息': 库,
            '分析结果': 分析结果
        }
    
    @classmethod
    def _收集视频(cls, 路径: str) -> List[Path]:
        """收集目录下的所有视频"""
        路径对象 = Path(路径)
        结果 = []
        for 后缀 in 视频后缀:
            结果.extend(路径对象.rglob(f"*{后缀}"))
            结果.extend(路径对象.rglob(f"*{后缀.upper()}"))
        return list(set(结果))
    
    @classmethod
    def _计算总大小(cls, 路径: str) -> int:
        """计算目录总大小"""
        视频列表 = cls._收集视频(路径)
        总大小 = 0
        for 视频路径 in 视频列表:
            try:
                总大小 += 视频路径.stat().st_size
            except:
                pass
        return 总大小


class 库管理器:
    """库管理主类"""
    
    def __init__(self):
        数据目录.mkdir(parents=True, exist_ok=True)
        with 库管理数据库() as _:
            pass
    
    def 添加库(self, 路径: str, 自动检测: bool = True) -> Dict:
        """添加新库"""
        路径 = str(Path(路径).absolute())
        
        if not os.path.exists(路径):
            return {'成功': False, '错误': '路径不存在'}
        
        if 自动检测:
            return 智能分类检测器.检测并标记库(路径)
        else:
            库 = 视频库(路径=路径, 分类状态='未分类')
            with 库管理数据库() as db:
                db.添加库(库)
            return {'成功': True, '库信息': 库}
    
    def 获取库列表(self) -> List[视频库]:
        """获取所有库"""
        with 库管理数据库() as db:
            return db.获取所有库()
    
    def 获取统计(self) -> Dict:
        """获取统计信息"""
        with 库管理数据库() as db:
            return db.获取统计概览()
    
    def 更新状态(self, 路径: str, 状态: str) -> bool:
        """更新库状态"""
        with 库管理数据库() as db:
            return db.更新库状态(路径, 状态)
    
    def 更新人物(self, 路径: str, 人物列表: List[str]) -> bool:
        """更新库关联人物"""
        with 库管理数据库() as db:
            return db.更新库人物(路径, 人物列表)
    
    def 删除库(self, 路径: str) -> bool:
        """删除库"""
        with 库管理数据库() as db:
            return db.删除库(路径)
    
    def 重新检测库(self, 路径: str) -> Dict:
        """重新检测库的分类状态"""
        路径 = str(Path(路径).absolute())
        return 智能分类检测器.检测并标记库(路径)


# 命令行接口
if __name__ == '__main__':
    import argparse
    
    解析器 = argparse.ArgumentParser(description='库管理模块')
    解析器.add_argument('命令', choices=['添加', '列表', '删除', '检测', '统计', '更新状态'])
    解析器.add_argument('路径', nargs='?')
    解析器.add_argument('--状态', choices=['未分类', '分类中', '已分类'])
    解析器.add_argument('--人物', help='逗号分隔的人物列表')
    
    参数 = 解析器.parse_args()
    
    管理器 = 库管理器()
    
    if 参数.命令 == '添加':
        if not 参数.路径:
            print("错误: 需要提供库路径")
            exit(1)
        结果 = 管理器.添加库(参数.路径)
        if '错误' in 结果:
            print(f"✗ {结果['错误']}")
        else:
            库 = 结果['库信息']
            print(f"✓ 添加库成功: {库.名称}")
            print(f"  状态: {库.分类状态}")
            print(f"  视频: {库.视频数量} 个")
            if 库.关联人物:
                print(f"  人物: {', '.join(库.关联人物)}")
    
    elif 参数.命令 == '列表':
        库列表 = 管理器.获取库列表()
        if not 库列表:
            print("暂无库记录")
        else:
            print(f"\n{'='*80}")
            print(f"视频库列表 ({len(库列表)} 个)")
            print(f"{'='*80}")
            for 库 in 库列表:
                状态图标 = {'未分类': '📦', '分类中': '⏳', '已分类': '✅'}.get(库.分类状态, '❓')
                大小 = f"{库.总大小/(1024**3):.1f}GB" if 库.总大小 > 0 else "未知"
                print(f"\n{状态图标} {库.名称}")
                print(f"   路径: {库.路径}")
                print(f"   状态: {库.分类状态} | 视频: {库.视频数量} 个 | 大小: {大小}")
                if 库.关联人物:
                    print(f"   人物: {', '.join(库.关联人物)}")
                if 库.备注:
                    print(f"   备注: {库.备注}")
            print(f"{'='*80}")
    
    elif 参数.命令 == '删除':
        if not 参数.路径:
            print("错误: 需要提供库路径")
            exit(1)
        if 管理器.删除库(参数.路径):
            print(f"✓ 删除成功")
        else:
            print(f"✗ 删除失败")
    
    elif 参数.命令 == '检测':
        if not 参数.路径:
            print("错误: 需要提供库路径")
            exit(1)
        结果 = 管理器.重新检测库(参数.路径)
        if '错误' in 结果:
            print(f"✗ {结果['错误']}")
        else:
            分析 = 结果['分析结果']
            print(f"\n📊 检测结果")
            print(f"{'='*50}")
            print(f"分类类型: {分析['分类类型']}")
            print(f"置信度: {分析['置信度']:.0%}")
            print(f"视频分布:")
            for 文件夹, 数量 in 分析['视频分布'].items():
                print(f"  - {文件夹}: {数量} 个视频")
            print(f"建议: {分析['建议']}")
    
    elif 参数.命令 == '统计':
        统计 = 管理器.获取统计()
        print(f"\n📈 统计概览")
        print(f"{'='*50}")
        print(f"库总数: {统计['库总数']} 个")
        print(f"  - 未分类: {统计['未分类']} 个")
        print(f"  - 分类中: {统计['分类中']} 个")
        print(f"  - 已分类: {统计['已分类']} 个")
        print(f"总视频: {统计['总视频数']} 个")
        print(f"总大小: {统计['总大小GB']:.1f} GB")
        print(f"总时长: {统计['总时长小时']:.1f} 小时")
    
    elif 参数.命令 == '更新状态':
        if not 参数.路径 or not 参数.状态:
            print("错误: 需要提供路径和状态")
            exit(1)
        if 管理器.更新状态(参数.路径, 参数.状态):
            print(f"✓ 状态更新为: {参数.状态}")
        else:
            print(f"✗ 更新失败")
