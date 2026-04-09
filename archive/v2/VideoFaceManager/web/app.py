#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoFaceManager Web管理面板
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, jsonify, request, send_file
import os

from core import Database, PersonLibrary, VideoScanner
from core.config import THUMBS_DIR, PERSON_LIBRARY_DIR

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

# 添加自定义过滤器
@app.template_filter('basename')
def basename_filter(path):
    """获取路径的文件名"""
    if not path:
        return ''
    return os.path.basename(str(path))

@app.template_filter('fromjson')
def fromjson_filter(s):
    """解析JSON字符串"""
    import json
    if not s:
        return []
    try:
        return json.loads(s)
    except:
        return []

# 全局实例
db = Database()
person_lib = PersonLibrary(db)


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """概览页"""
    stats = db.get_stats()
    persons = db.get_all_persons()
    recent_videos = db.get_all_videos(limit=6)
    
    return render_template('index.html', 
                         stats=stats, 
                         persons=persons,
                         recent_videos=recent_videos)


@app.route('/videos')
def videos():
    """视频库页面"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    all_videos = db.get_all_videos(limit=per_page, offset=(page-1)*per_page)
    total = db.get_stats()['video_count']
    
    return render_template('videos.html',
                         videos=all_videos,
                         page=page,
                         total_pages=(total // per_page) + 1,
                         total=total)


@app.route('/video/<int:video_id>')
def video_detail(video_id):
    """视频详情页"""
    video = db.get_video_by_id(video_id)
    if not video:
        return "视频不存在", 404
    
    # 获取视频中的人物
    persons = db.get_video_persons(video_id)
    
    return render_template('video_detail.html',
                         video=video,
                         persons=persons)


@app.route('/persons')
def persons():
    """人物列表页"""
    all_persons = db.get_all_persons()
    
    # 统计每个人物出现的视频数
    for p in all_persons:
        videos = db.get_person_videos(p['id'])
        p['video_count'] = len(videos)
    
    return render_template('persons.html', persons=all_persons)


@app.route('/person/<int:person_id>')
def person_detail(person_id):
    """人物详情页"""
    person = db.get_person_by_id(person_id)
    if not person:
        return "人物不存在", 404
    
    videos = db.get_person_videos(person_id)
    
    return render_template('person_detail.html',
                         person=person,
                         videos=videos)


# ==================== API接口 ====================

@app.route('/api/stats')
def api_stats():
    """获取统计信息"""
    return jsonify(db.get_stats())


@app.route('/api/videos')
def api_videos():
    """获取视频列表"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    videos = db.get_all_videos(limit=limit, offset=(page-1)*limit)
    return jsonify(videos)


@app.route('/api/video/<int:video_id>/persons', methods=['GET', 'POST'])
def api_video_persons(video_id):
    """获取或修改视频的人物"""
    if request.method == 'GET':
        persons = db.get_video_persons(video_id)
        return jsonify(persons)
    
    elif request.method == 'POST':
        data = request.get_json()
        persons = data.get('persons', [])
        db.update_video_persons(video_id, persons)
        return jsonify({'success': True})


@app.route('/api/persons')
def api_persons():
    """获取人物列表"""
    persons = db.get_all_persons()
    return jsonify(persons)


@app.route('/api/person/<int:person_id>')
def api_person_detail(person_id):
    """获取人物详情"""
    person = db.get_person_by_id(person_id)
    if person:
        videos = db.get_person_videos(person_id)
        person['videos'] = videos
        return jsonify(person)
    return jsonify({'error': 'not found'}), 404


@app.route('/api/person/<int:person_id>', methods=['DELETE'])
def api_delete_person(person_id):
    """删除人物"""
    db.delete_person(person_id)
    return jsonify({'success': True})


# ==================== 文件服务 ====================

@app.route('/thumb/<path:filename>')
def serve_thumb(filename):
    """提供缩略图"""
    return send_file(THUMBS_DIR / filename)


@app.route('/person_face/<name>')
def serve_person_face(name):
    """提供人物头像"""
    person_dir = PERSON_LIBRARY_DIR / name
    if person_dir.exists():
        # 找第一张图片
        for img_path in person_dir.iterdir():
            if img_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                return send_file(img_path)
    return "", 404


# ==================== 启动 ====================

def main():
    print("="*50)
    print("🎬 VideoFaceManager 管理面板")
    print("="*50)
    print("\n启动中...")
    
    # 检查数据目录
    from core.config import DATA_DIR
    DATA_DIR.mkdir(exist_ok=True)
    
    print(f"\n数据库: {db.db_path}")
    print(f"人物库: {person_lib.library_dir}")
    
    stats = db.get_stats()
    print(f"\n当前数据:")
    print(f"  视频: {stats['video_count']} 个")
    print(f"  人物: {stats['person_count']} 个")
    
    print("\n" + "="*50)
    print("请在浏览器打开: http://localhost:5000")
    print("按 Ctrl+C 停止")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
