#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合模式 CLI - 反向学习 + 主动录入 + 纠正
"""
import sys
import click
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core import Database, PersonLibrary, VideoScanner
from core.video_learner import VideoLearner
from core.hybrid_library import HybridPersonLibrary
from core.hybrid_recognizer import HybridRecognizer


@click.group()
def cli():
    """视频人物花名册管理系统 - 综合模式"""
    pass


@cli.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--recursive', '-r', is_flag=True, default=True, help='递归扫描子目录')
def scan(directory, recursive):
    """扫描视频文件夹，识别人物"""
    scanner = VideoScanner()
    scanner.batch_scan(directory, recursive)


# ========== 学习命令 ==========

@cli.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--min-samples', '-m', default=5, help='每个人物最少样本数')
@click.option('--max-samples', '-x', default=20, help='每个人物最多样本数')
@click.option('--save-faces', '-s', is_flag=True, default=True, help='保存人脸截图')
def learn(directory, min_samples, max_samples, save_faces):
    """从已分类视频中学习人物特征（反向学习）"""
    learner = VideoLearner()
    learner.learn_from_videos(directory, min_samples, max_samples, save_faces)


@cli.command()
@click.argument('directory', type=click.Path(exists=True))
def add_photos(directory):
    """主动录入 - 从照片导入人物特征
    
    目录结构:
        照片文件夹/
        ├── 张三/
        │   ├── 正面照.jpg
        │   └── 侧面照.jpg
        └── 李四/
            └── 照片.png
    """
    print("\n📸 主动录入 - 导入人物照片")
    print("="*60)
    
    lib = HybridPersonLibrary()
    root = Path(directory)
    
    for person_dir in root.iterdir():
        if not person_dir.is_dir():
            continue
        
        person_name = person_dir.name
        
        # 收集照片
        photos = []
        for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']:
            photos.extend(person_dir.glob(f'*{ext}'))
            photos.extend(person_dir.glob(f'*{ext.upper()}'))
        
        if not photos:
            continue
        
        print(f"\n👤 {person_name} - 处理 {len(photos)} 张照片")
        
        features = []
        for photo_path in photos:
            try:
                import cv2
                img = cv2.imread(str(photo_path))
                if img is None:
                    continue
                
                faces = lib.face_app.get(img)
                if faces:
                    face = max(faces, key=lambda x: 
                              (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
                    if face.det_score >= 0.8:
                        features.append(face.embedding.tolist())
                        print(f"  ✓ {photo_path.name}")
                    else:
                        print(f"  ⚠ {photo_path.name} - 人脸质量低")
                else:
                    print(f"  ✗ {photo_path.name} - 未检测到人脸")
            except Exception as e:
                print(f"  ✗ {photo_path.name} - 错误: {e}")
        
        if features:
            lib.add_features(person_name, features, 
                           HybridPersonLibrary.SOURCE_PHOTO,
                           {'photo_count': len(photos)})
    
    print("\n✅ 照片导入完成!")


@cli.command()
@click.option('--videos', '-v', type=click.Path(exists=True), 
              help='已分类视频文件夹')
@click.option('--photos', '-p', type=click.Path(exists=True),
              help='人物照片文件夹')
def build(videos, photos):
    """综合建库 - 同时使用反向学习+主动录入"""
    recognizer = HybridRecognizer()
    recognizer.build_library(
        classified_videos=videos,
        photo_library=photos
    )


# ========== 识别命令 ==========

@cli.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--output', '-o', default='./已识别', help='输出目录')
@click.option('--auto-move', '-m', is_flag=True, help='自动按人物分类移动视频')
@click.option('--min-confidence', '-c', default=0.65, help='最小置信度(0-1)')
def identify(directory, output, auto_move, min_confidence):
    """识别未分类视频中的人物（使用混合特征库）"""
    recognizer = HybridRecognizer()
    recognizer.batch_recognize(
        video_dir=directory,
        output_dir=output,
        min_confidence=min_confidence,
        auto_organize=auto_move
    )


# ========== 纠正命令 ==========

@cli.command()
@click.argument('video_path', type=click.Path(exists=True))
@click.argument('person_name')
@click.option('--positive/--negative', default=True, 
              help='正反馈(确认正确)或负反馈(标记错误)')
def correct(video_path, person_name, positive):
    """纠正反馈 - 修正识别结果
    
    示例:
        # 确认视频里确实是张三
        python cli.py correct /path/video.mp4 张三 --positive
        
        # 标记视频里不是李四
        python cli.py correct /path/video.mp4 李四 --negative
    """
    lib = HybridPersonLibrary()
    
    if positive:
        print(f"✓ 记录正反馈: {Path(video_path).name} 包含 {person_name}")
        lib.add_correction(video_path, person_name, is_positive=True)
        print("  已添加为可信样本，将提高该人物识别权重")
    else:
        print(f"✗ 记录负反馈: {Path(video_path).name} 不包含 {person_name}")
        lib.add_correction(video_path, person_name, is_positive=False)
        print("  已记录错误匹配，将排除该关联")


@cli.command()
@click.argument('video_path', type=click.Path(exists=True))
def identify_one(video_path):
    """识别单个视频并显示详细信息"""
    recognizer = HybridRecognizer()
    
    print(f"\n🔍 识别: {Path(video_path).name}")
    print("="*60)
    
    results = recognizer.recognize(video_path, min_confidence=0.5)
    
    if results:
        print(f"\n识别到 {len(results)} 个人物:\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r['name']}")
            print(f"     置信度: {r['confidence']:.1%}")
            print(f"     特征来源: {r['source']}")
            print(f"     出现次数: {r['appearances']}次")
            print(f"     时间点: {', '.join(f'{t:.1f}s' for t in r['timestamps'])}")
            print()
    else:
        print("❓ 未识别出人物")
    
    # 提示纠正
    print("-"*60)
    print("如果识别结果不正确，可以使用以下命令纠正:")
    print(f"  python cli.py correct \"{video_path}\" [正确人名] --positive")
    print(f"  python cli.py correct \"{video_path}\" [错误人名] --negative")


# ========== 管理命令 ==========

@cli.command()
def stats():
    """查看统计信息"""
    db = Database()
    lib = HybridPersonLibrary()
    
    stats = db.get_stats()
    
    print("\n" + "="*60)
    print("📊 花名册统计")
    print("="*60)
    print(f"视频总数: {stats['video_count']}")
    print(f"人物总数: {stats['person_count']}")
    print(f"未识别视频: {stats['unknown_count']}")
    print(f"总容量: {stats['total_size'] / (1024**3):.2f} GB")
    
    # 显示人物库详情
    persons = db.get_all_persons()
    if persons:
        print("\n📚 人物库详情:")
        for p in persons:
            s = lib.get_person_stats(p['name'])
            print(f"  {p['name']:12s} {s['total_features']:2d}特征 "
                  f"[照片{s['by_source'].get('photo',0)} "
                  f"视频{s['by_source'].get('video',0)} "
                  f"纠正{s['by_source'].get('correct',0)}] "
                  f"可信度:{s['confidence']}")
    
    print("="*60)


@cli.command()
def persons():
    """查看人物库"""
    lib = HybridPersonLibrary()
    db = Database()
    persons = db.get_all_persons()
    
    if not persons:
        print("\n⚠ 人物库为空")
        print("请先运行:")
        print("  python cli.py build --videos /已分类视频")
        print("  python cli.py add_photos /人物照片")
        return
    
    print("\n" + "="*60)
    print(f"📚 人物库 ({len(persons)} 个人物)")
    print("="*60)
    
    for p in persons:
        stats = lib.get_person_stats(p['name'])
        print(f"\n👤 {p['name']}")
        print(f"   总特征: {stats['total_features']}个")
        print(f"   可信度: {stats['confidence']}")
        
        by_src = stats['by_source']
        sources = []
        if by_src.get('photo', 0) > 0:
            sources.append(f"主动录入{by_src['photo']}")
        if by_src.get('video', 0) > 0:
            sources.append(f"反向学习{by_src['video']}")
        if by_src.get('correct', 0) > 0:
            sources.append(f"纠正反馈{by_src['correct']}")
        
        if sources:
            print(f"   来源: {', '.join(sources)}")
    
    print("="*60)


@cli.command()
@click.argument('person1')
@click.argument('person2')
@click.option('--new-name', '-n', help='合并后的新名字（默认保留第一个）')
def merge(person1, person2, new_name):
    """合并两个人物（如果发现是同一人）"""
    lib = HybridPersonLibrary()
    
    if click.confirm(f'确定将 "{person1}" 和 "{person2}" 合并为 "{new_name or person1}" 吗?'):
        success = lib.merge_similar_persons(person1, person2, new_name)
        if success:
            print(f"✓ 合并完成")
        else:
            print(f"✗ 合并失败")


@cli.command()
@click.argument('person_name')
@click.argument('output_dir', type=click.Path())
def export(person_name, output_dir):
    """导出人物数据（备份或迁移）"""
    lib = HybridPersonLibrary()
    success = lib.export_person_data(person_name, output_dir)
    if success:
        print(f"✓ 已导出到 {output_dir}/{person_name}.json")


@cli.command()
@click.argument('import_file', type=click.Path(exists=True))
def import_person(import_file):
    """导入人物数据"""
    lib = HybridPersonLibrary()
    success = lib.import_person_data(import_file)
    if success:
        print("✓ 导入完成")


@cli.command()
def init():
    """初始化系统"""
    from core.config import DATA_DIR, PERSON_LIBRARY_DIR, THUMBS_DIR, FACES_DIR
    
    print("\n🔧 初始化系统...")
    
    DATA_DIR.mkdir(exist_ok=True)
    PERSON_LIBRARY_DIR.mkdir(exist_ok=True)
    THUMBS_DIR.mkdir(exist_ok=True)
    FACES_DIR.mkdir(exist_ok=True)
    
    db = Database()
    
    print(f"✓ 数据目录: {DATA_DIR}")
    print(f"✓ 人物库: {PERSON_LIBRARY_DIR}")
    print(f"✓ 人脸截图: {FACES_DIR}")
    print(f"✓ 数据库已初始化")
    print("\n使用方法:")
    print("  1. 建库: python cli.py build --videos /已分类视频")
    print("  2. 识别: python cli.py identify /未分类视频 -o /输出 --auto-move")
    print("  3. 纠正: python cli.py correct /视频 人名 --positive/--negative")
    print("  4. 面板: python manager.py")


if __name__ == '__main__':
    cli()