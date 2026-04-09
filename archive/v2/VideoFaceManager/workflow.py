#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoFaceManager 完整工作流示例
从已分类视频学习 → 识别新视频 → 生成标识
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core import VideoLearner


def main():
    """
    演示完整工作流程
    """
    print("="*60)
    print("🎬 VideoFaceManager 完整工作流演示")
    print("="*60)
    
    # ========== 第一步：从已分类视频学习 ==========
    print("\n📚 第一步：从已分类视频学习人物特征")
    print("-"*60)
    
    # 你的已分类视频文件夹路径
    classified_dir = input("请输入已分类视频文件夹路径 (例如 D:/已分类视频): ").strip()
    
    if not classified_dir:
        print("使用示例路径: ./示例/已分类")
        classified_dir = "./示例/已分类"
    
    learner = VideoLearner()
    
    # 学习
    results = learner.learn_from_videos(
        root_dir=classified_dir,
        min_samples=5,      # 每人最少5个样本
        max_samples=20,     # 每人最多20个样本
        save_faces=True     # 保存人脸截图
    )
    
    if not results:
        print("\n✗ 学习失败，请检查目录结构")
        return
    
    # ========== 第二步：识别新视频 ==========
    print("\n🔍 第二步：识别未分类视频")
    print("-"*60)
    
    unclassified_dir = input("请输入未分类视频文件夹路径: ").strip()
    
    if not unclassified_dir:
        print("使用示例路径: ./示例/未分类")
        unclassified_dir = "./示例/未分类"
    
    output_dir = input("请输入输出目录 (默认: ./已识别): ").strip() or "./已识别"
    
    # 识别
    identified = learner.identify_videos(
        video_dir=unclassified_dir,
        output_dir=output_dir,
        auto_move=True,          # 自动按人物分类
        min_confidence=0.65      # 最小置信度65%
    )
    
    # ========== 第三步：生成标识文件 ==========
    print("\n🏷 第三步：生成标识文件")
    print("-"*60)
    
    generate_tags(identified, output_dir)
    
    print("\n" + "="*60)
    print("✅ 工作流完成！")
    print("="*60)
    print(f"\n输出目录: {output_dir}")
    print("包含:")
    print("  📁 人物名/       - 按人物分类的视频")
    print("  📁 未识别/       - 未识别出人物的视频")
    print("  📄 识别报告.json - 详细识别结果")
    print("  📄 人物标签.txt  - 视频标签列表")
    print("\n你可以:")
    print("  1. 检查分类结果")
    print("  2. 把错误分类的视频移回正确位置")
    print("  3. 重新运行 learn 来改进识别准确度")
    print("="*60)


def generate_tags(identified: dict, output_dir: str):
    """生成人物标签文件"""
    output_path = Path(output_dir)
    
    # 生成标签列表
    tag_file = output_path / "人物标签.txt"
    with open(tag_file, 'w', encoding='utf-8') as f:
        f.write("视频人物标签列表\n")
        f.write("="*50 + "\n\n")
        
        for person_name, videos in identified.items():
            f.write(f"\n【{person_name}】\n")
            f.write("-"*50 + "\n")
            for v in videos:
                f.write(f"  📹 {v['video_name']}\n")
                f.write(f"     置信度: {v['confidence']:.1%}\n")
                f.write(f"     出现时间: {format_timestamps(v['timestamps'])}\n")
                f.write(f"     路径: {v['video_path']}\n\n")
    
    print(f"✓ 标签文件已生成: {tag_file}")
    
    # 生成CSV表格（方便Excel查看）
    csv_file = output_path / "识别结果.csv"
    with open(csv_file, 'w', encoding='utf-8-sig') as f:  # utf-8-sig for Excel
        f.write("人物,视频文件名,置信度,出现次数,视频路径\n")
        for person_name, videos in identified.items():
            for v in videos:
                f.write(f"{person_name},{v['video_name']},{v['confidence']:.2%},{len(v['timestamps'])},{v['video_path']}\n")
    
    print(f"✓ CSV表格已生成: {csv_file}")


def format_timestamps(timestamps: list) -> str:
    """格式化时间戳"""
    if not timestamps:
        return "未知"
    
    # 取前3个时间点显示
    times = [f"{int(t//60):02d}:{int(t%60):02d}" for t in timestamps[:3]]
    result = ", ".join(times)
    
    if len(timestamps) > 3:
        result += f" 等{len(timestamps)}处"
    
    return result


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户取消操作")
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()