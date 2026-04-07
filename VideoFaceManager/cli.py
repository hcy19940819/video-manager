#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoFaceManager CLI - 命令行入口
"""
import sys
import click
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core import Database, PersonLibrary, VideoScanner


@click.group()
def cli():
    """视频人物花名册管理系统"""
    pass


@cli.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--recursive', '-r', is_flag=True, default=True, help='递归扫描子目录')
def scan(directory, recursive):
    """扫描视频文件夹，识别人物"""
    scanner = VideoScanner()
    scanner.batch_scan(directory, recursive)


@cli.command()
def stats():
    """查看统计信息"""
    db = Database()
    stats = db.get_stats()
    
    print("\n" + "="*40)
    print("📊 花名册统计")
    print("="*40)
    print(f"视频总数: {stats['video_count']}")
    print(f"人物总数: {stats['person_count']}")
    print(f"未识别视频: {stats['unknown_count']}")
    print(f"总容量: {stats['total_size'] / (1024**3):.2f} GB")
    print("="*40)


@cli.command()
def persons():
    """查看人物库"""
    lib = PersonLibrary()
    persons = lib.scan_library()
    
    if not persons:
        print("\n⚠ 人物库为空")
        print(f"请在文件夹中创建人物子文件夹:")
        print(f"  {lib.library_dir}")
        return
    
    print("\n" + "="*50)
    print(f"📚 人物库 ({len(persons)} 个人物)")
    print("="*50)
    
    for p in persons:
        status = "✓" if p['in_database'] else "○"
        print(f"{status} {p['name']:12s} - {p['image_count']}张照片", end="")
        if p['in_database']:
            print(f" (已提取{p['face_count']}个特征)")
        else:
            print(" (未导入)")
    
    print("="*50)


@cli.command()
@click.argument('name')
@click.argument('image_paths', nargs=-1, required=True)
def add_person(name, image_paths):
    """添加人物照片"""
    lib = PersonLibrary()
    
    print(f"\n添加人物: {name}")
    print(f"照片数量: {len(image_paths)}")
    
    success = lib.add_person_images(name, list(image_paths))
    
    if success:
        print(f"\n✓ 人物 '{name}' 添加成功")
    else:
        print(f"\n✗ 添加失败")


@cli.command()
@click.argument('name')
def remove_person(name):
    """删除人物"""
    lib = PersonLibrary()
    
    if click.confirm(f'确定删除人物 "{name}" 吗?'):
        success = lib.delete_person(name)
        if success:
            print(f"✓ 已删除: {name}")
        else:
            print(f"✗ 删除失败或人物不存在")


@cli.command()
def init():
    """初始化系统（创建数据库和目录）"""
    from core.config import DATA_DIR, PERSON_LIBRARY_DIR, THUMBS_DIR, FACES_DIR
    
    print("\n🔧 初始化系统...")
    
    # 创建目录
    DATA_DIR.mkdir(exist_ok=True)
    PERSON_LIBRARY_DIR.mkdir(exist_ok=True)
    THUMBS_DIR.mkdir(exist_ok=True)
    FACES_DIR.mkdir(exist_ok=True)
    
    # 初始化数据库
    db = Database()
    
    print(f"✓ 数据目录: {DATA_DIR}")
    print(f"✓ 人物库: {PERSON_LIBRARY_DIR}")
    print(f"✓ 数据库已初始化")
    print("\n下一步:")
    print("  1. 在人物库文件夹创建人物子文件夹")
    print("  2. 放入人物照片")
    print("  3. 运行: python cli.py scan /视频文件夹")


if __name__ == '__main__':
    cli()
