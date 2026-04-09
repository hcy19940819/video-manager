"""
配置参数
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PERSON_LIBRARY_DIR = DATA_DIR / "person_library"
THUMBS_DIR = DATA_DIR / "thumbs"
FACES_DIR = DATA_DIR / "faces"
DB_PATH = DATA_DIR / "video_persons.db"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
PERSON_LIBRARY_DIR.mkdir(exist_ok=True)
THUMBS_DIR.mkdir(exist_ok=True)
FACES_DIR.mkdir(exist_ok=True)

# 视频格式
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', 
                    '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts', '.vob'}

# 人脸识别配置
FACE_DETECTION_THRESHOLD = 0.5  # 人脸检测阈值
FACE_MATCH_THRESHOLD = 0.6      # 人脸匹配阈值（相似度>此值认为是同一人）

# 识别配置
SAMPLE_INTERVAL = 5             # 每5秒采样一帧
MAX_FACES_PER_VIDEO = 50        # 单个视频最多提取50个人脸
MAX_FACES_PER_PERSON = 10       # 人物库每人最多用10张参考照片

# 硬件配置
USE_GPU = True                  # 是否使用GPU
GPU_PROVIDER = "CUDA"           # CUDA / DirectML / CPU

# 窗口大小
VIDEO_THUMB_WIDTH = 320
VIDEO_THUMB_HEIGHT = 180
FACE_THUMB_SIZE = 150
