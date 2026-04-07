#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合模式一键工作流
整合: 反向学习 + 主动录入 + 批量识别 + 纠正反馈
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core import Database
from core.hybrid_recognizer import HybridRecognizer
from core.hybrid_library import HybridPersonLibrary


def main():
    """交互式综合工作流"""
    print("="*70)
    print("🎬 VideoFaceManager 综合模式")
    print("   反向学习 + 主动录入 + 智能识别 + 纠正反馈")
    print("="*70)
    
    recognizer = HybridRecognizer()
    lib = HybridPersonLibrary()
    
    # ========== 阶段1: 构建人物库 ==========
    print("\n📚 阶段1: 构建人物库")
    print("-"*70)
    print("\n支持两种方式构建人物库（可以同时使用）:")
    print("  1️⃣  反向学习 - 从已分类的视频中学习")
    print("  2️⃣  主动录入 - 从照片中导入")
    print()
    
    use_videos = input("是否有已分类的视频文件夹? (y/n): ").lower() == 'y'
    video_dir = None
    if use_videos:
        video_dir = input("请输入已分类视频文件夹路径: ").strip()
    
    use_photos = input("\n是否有人物照片文件夹? (y/n): ").lower() == 'y'
    photo_dir = None
    if use_photos:
        photo_dir = input("请输入人物照片文件夹路径: ").strip()
    
    if not use_videos and not use_photos:
        print("\n⚠ 没有提供任何人物库来源，退出")
        return
    
    # 构建库
    recognizer.build_library(
        classified_videos=video_dir,
        photo_library=photo_dir
    )
    
    # 检查人物库
    persons = lib.db.get_all_persons()
    if not persons:
        print("\n✗ 人物库为空，无法继续")
        return
    
    print(f"\n✅ 人物库构建完成，共 {len(persons)} 个人物")
    
    # ========== 阶段2: 批量识别 ==========
    print("\n" + "="*70)
    print("🔍 阶段2: 批量识别视频")
    print("-"*70)
    
    input_dir = input("\n请输入待识别的视频文件夹: ").strip()
    if not input_dir:
        print("⚠ 未提供输入目录，跳过识别")
        return
    
    output_dir = input("请输入输出目录 (默认: ./已识别): ").strip() or "./已识别"
    
    # 调整置信度
    conf = input("\n设置识别置信度阈值 (0.5-0.9, 默认0.65): ").strip()
    min_conf = float(conf) if conf else 0.65
    
    print(f"\n将使用 {min_conf:.0%} 作为置信度阈值")
    print("  - 阈值高: 准确率高但可能漏识别")
    print("  - 阈值低: 识别全但可能有误报")
    
    auto_organize = input("\n是否自动按人物整理视频? (y/n, 默认y): ").lower() != 'n'
    
    # 执行识别
    recognizer.batch_recognize(
        video_dir=input_dir,
        output_dir=output_dir,
        min_confidence=min_conf,
        auto_organize=auto_organize
    )
    
    # ========== 阶段3: 纠正反馈 ==========
    print("\n" + "="*70)
    print("✏️ 阶段3: 纠正反馈（可选）")
    print("-"*70)
    
    print("\n如果识别结果有错误，可以通过以下方式纠正:")
    print()
    print("  1. 打开Web管理面板查看详情:")
    print("     python manager.py")
    print("     浏览器访问 http://localhost:5000")
    print()
    print("  2. 使用命令行纠正:")
    print("     # 确认某视频确实包含某人")
    print(f'     python cli_hybrid.py correct "视频路径" 人名 --positive')
    print()
    print("     # 标记某视频不包含某人")
    print(f'     python cli_hybrid.py correct "视频路径" 人名 --negative')
    print()
    
    do_correct = input("是否现在进行纠正? (y/n, 默认n): ").lower() == 'y'
    
    if do_correct:
        while True:
            print("\n-"*70)
            video = input("视频文件名 (或回车结束): ").strip()
            if not video:
                break
            
            video_path = Path(input_dir) / video
            if not video_path.exists():
                print(f"✗ 文件不存在: {video}")
                continue
            
            print(f"\n当前人物: {', '.join(p['name'] for p in persons)}")
            person = input("人物名: ").strip()
            
            correct_type = input("类型? (1=确认正确, 2=标记错误): ").strip()
            is_positive = correct_type == '1'
            
            lib.add_correction(str(video_path), person, is_positive)
            
            print(f"✓ 已记录{'正' if is_positive else '负'}反馈")
            
            more = input("\n是否继续纠正? (y/n): ").lower()
            if more != 'y':
                break
    
    # ========== 完成 ==========
    print("\n" + "="*70)
    print("✅ 综合工作流完成!")
    print("="*70)
    print(f"\n📁 输出目录: {output_dir}")
    print("\n包含内容:")
    print("  📂 人物名/        - 按人物分类的视频")
    print("  📂 未识别/        - 未识别出人物的视频")
    print("  📄 识别报告.json  - 详细数据")
    print("  📄 人物标签.txt   - 人读格式")
    print()
    print("后续操作:")
    print("  1. 检查分类结果，把错分的视频移到正确位置")
    print("  2. 运行纠正反馈，提高识别准确度")
    print("  3. 重新运行本脚本，迭代优化")
    print("="*70)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ 用户取消")
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")
