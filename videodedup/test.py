#!/usr/bin/env python3
"""
VideoDedup 测试脚本 - 验证核心功能
"""

import os
import sys
import tempfile
import shutil

# 添加上级目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_database():
    """测试数据库功能"""
    print("测试数据库...")
    
    from videodedup import FingerprintDB, VideoFingerprint
    
    # 创建临时数据库
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        with FingerprintDB(db_path) as db:
            # 创建测试指纹
            fp = VideoFingerprint(
                path="/test/video1.mp4",
                size=1024000,
                mtime=1234567890,
                duration=120.5,
                width=1920,
                height=1080,
                quick_hash="aabbccdd11223344",
                detail_hashes=["hash1", "hash2", "hash3"],
                file_hash="md5hash123"
            )
            
            # 保存
            assert db.save_fingerprint(fp), "保存指纹失败"
            
            # 读取
            loaded = db.get_fingerprint("/test/video1.mp4")
            assert loaded is not None, "读取指纹失败"
            assert loaded.path == fp.path, "路径不匹配"
            assert loaded.size == fp.size, "大小不匹配"
            assert loaded.quick_hash == fp.quick_hash, "快速哈希不匹配"
            
            print("✓ 数据库测试通过")
            
    finally:
        os.unlink(db_path)

def test_similarity():
    """测试相似度计算"""
    print("测试相似度计算...")
    
    from videodedup import SimilarityCalculator, VideoFingerprint
    
    calc = SimilarityCalculator()
    
    # 测试汉明距离
    dist = calc.hamming_distance("aabbccdd11223344", "aabbccdd11223345")
    print(f"  汉明距离: {dist}")
    
    # 测试序列相似度
    sim = calc.sequence_similarity(["hash1", "hash2", "hash3"], ["hash1", "hash2", "hash4"])
    print(f"  序列相似度: {sim:.2f}")
    
    # 测试重复判断
    fp1 = VideoFingerprint(path="/a/1.mp4", size=1000, mtime=1, quick_hash="aabbccdd11223344")
    fp2 = VideoFingerprint(path="/b/1.mp4", size=1000, mtime=1, quick_hash="aabbccdd11223344")
    
    is_dup, reason = calc.are_duplicates(fp1, fp2)
    print(f"  重复判断: {is_dup}, 原因: {reason}")
    
    print("✓ 相似度测试通过")

def test_video_detection():
    """测试视频文件检测"""
    print("测试视频文件收集...")
    
    from videodedup import VideoDedup
    from pathlib import Path
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建一些测试文件
        (Path(tmpdir) / "video1.mp4").touch()
        (Path(tmpdir) / "video2.avi").touch()
        (Path(tmpdir) / "notvideo.txt").touch()
        (Path(tmpdir) / "subdir").mkdir()
        (Path(tmpdir) / "subdir" / "video3.mkv").touch()
        
        dedup = VideoDedup()
        videos = dedup._collect_videos(tmpdir)
        
        assert len(videos) == 3, f"应该找到3个视频，实际找到{len(videos)}"
        print(f"  找到 {len(videos)} 个视频文件")
        print("✓ 视频文件检测测试通过")

def main():
    print("="*50)
    print("VideoDedup 功能测试")
    print("="*50)
    print()
    
    try:
        test_database()
        test_similarity()
        test_video_detection()
        
        print()
        print("="*50)
        print("所有测试通过!")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
