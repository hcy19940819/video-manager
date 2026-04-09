#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoDedup HTML Report Generator - 可视化报告生成器
生成带有缩略图、对比、勾选功能的HTML报告
"""

import os
import json
import base64
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from dataclasses import dataclass
import tempfile
import shutil

# 尝试导入视频处理
try:
    import cv2
    import numpy as np
    from PIL import Image
    HAS_VIDEO = True
except ImportError:
    HAS_VIDEO = False


class HTMLReportGenerator:
    """生成可视化HTML报告"""
    
    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="videodedup_report_")
        os.makedirs(self.output_dir, exist_ok=True)
        self.thumbnail_dir = Path(self.output_dir) / "thumbnails"
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_generated = {}
    
    def generate_thumbnail(self, video_path: str, size: tuple = (200, 150)) -> str:
        """生成视频缩略图，返回相对路径"""
        if not HAS_VIDEO:
            return None
        
        try:
            # 检查是否已生成
            if video_path in self.thumbnails_generated:
                return self.thumbnails_generated[video_path]
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # 获取视频时长，取中间帧
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return None
            
            # 转换为RGB并调整大小
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # 保存
            video_hash = str(hash(video_path) % 10000000)
            thumb_path = self.thumbnail_dir / f"thumb_{video_hash}.jpg"
            img.save(thumb_path, "JPEG", quality=85)
            
            rel_path = f"thumbnails/thumb_{video_hash}.jpg"
            self.thumbnails_generated[video_path] = rel_path
            return rel_path
            
        except Exception as e:
            print(f"生成缩略图失败 {video_path}: {e}")
            return None
    
    def generate_html(self, groups: List[Dict], output_file: str = None) -> str:
        """生成完整的HTML报告"""
        if output_file is None:
            output_file = os.path.join(self.output_dir, "report.html")
        
        html_content = self._build_html(groups)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_file
    
    def _build_html(self, groups: List[Dict]) -> str:
        """构建HTML内容"""
        total_videos = sum(len(g['videos']) for g in groups)
        total_groups = len(groups)
        
        # 计算可释放空间
        total_savings = 0
        for g in groups:
            sizes = sorted([v['size'] for v in g['videos']], reverse=True)
            total_savings += sum(sizes[1:])
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VideoDedup 重复视频报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header .meta {{ opacity: 0.9; font-size: 14px; }}
        
        .stats {{
            display: flex;
            gap: 20px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        
        .stat-card {{
            background: rgba(255,255,255,0.15);
            padding: 15px 25px;
            border-radius: 10px;
            backdrop-filter: blur(10px);
        }}
        
        .stat-card .number {{
            font-size: 32px;
            font-weight: bold;
            display: block;
        }}
        
        .stat-card .label {{ font-size: 12px; opacity: 0.8; }}
        
        .toolbar {{
            background: white;
            padding: 15px 30px;
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .btn {{
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }}
        
        .btn-primary {{
            background: #667eea;
            color: white;
        }}
        
        .btn-primary:hover {{ background: #5a6fd6; }}
        
        .btn-danger {{
            background: #e74c3c;
            color: white;
        }}
        
        .btn-danger:hover {{ background: #c0392b; }}
        
        .btn-secondary {{
            background: #ecf0f1;
            color: #333;
        }}
        
        .btn-secondary:hover {{ background: #d5dbdb; }}
        
        .search-box {{
            padding: 10px 15px;
            border: 1px solid #ddd;
            border-radius: 6px;
            width: 250px;
            font-size: 14px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .group {{
            background: white;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            overflow: hidden;
        }}
        
        .group-header {{
            background: #f8f9fa;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .group-title {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .group-number {{
            background: #667eea;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 14px;
        }}
        
        .group-badge {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }}
        
        .badge-identical {{ background: #d4edda; color: #155724; }}
        .badge-similar {{ background: #fff3cd; color: #856404; }}
        .badge-different-version {{ background: #d1ecf1; color: #0c5460; }}
        .badge-maybe {{ background: #f8d7da; color: #721c24; }}
        
        .group-info {{
            font-size: 13px;
            color: #666;
            margin-top: 5px;
        }}
        
        .video-list {{
            padding: 10px;
        }}
        
        .video-item {{
            display: flex;
            align-items: center;
            padding: 15px;
            border-bottom: 1px solid #f0f0f0;
            transition: background 0.2s;
        }}
        
        .video-item:hover {{ background: #f8f9fa; }}
        
        .video-item:last-child {{ border-bottom: none; }}
        
        .video-checkbox {{
            margin-right: 15px;
        }}
        
        .video-checkbox input[type="checkbox"] {{
            width: 20px;
            height: 20px;
            cursor: pointer;
        }}
        
        .video-thumb {{
            width: 160px;
            height: 120px;
            background: #f0f0f0;
            border-radius: 8px;
            margin-right: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            flex-shrink: 0;
        }}
        
        .video-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        
        .video-thumb .no-thumb {{
            color: #999;
            font-size: 12px;
            text-align: center;
        }}
        
        .video-info {{
            flex: 1;
            min-width: 0;
        }}
        
        .video-name {{
            font-weight: 600;
            font-size: 15px;
            margin-bottom: 5px;
            word-break: break-all;
            color: #2c3e50;
        }}
        
        .video-path {{
            font-size: 12px;
            color: #7f8c8d;
            font-family: monospace;
            margin-bottom: 8px;
            word-break: break-all;
        }}
        
        .video-meta {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            font-size: 13px;
        }}
        
        .video-meta span {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        
        .meta-size {{ color: #27ae60; }}
        .meta-duration {{ color: #3498db; }}
        .meta-resolution {{ color: #9b59b6; }}
        
        .video-actions {{
            display: flex;
            gap: 8px;
        }}
        
        .action-btn {{
            padding: 6px 12px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }}
        
        .action-btn:hover {{ background: #f0f0f0; }}
        
        .keep-badge {{
            background: #27ae60;
            color: white;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        }}
        
        .delete-badge {{
            background: #e74c3c;
            color: white;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        }}
        
        .selected-summary {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-top: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        
        .selected-summary h3 {{
            margin-bottom: 15px;
            color: #2c3e50;
        }}
        
        .summary-stats {{
            display: flex;
            gap: 30px;
            margin-bottom: 15px;
        }}
        
        .summary-item {{
            text-align: center;
        }}
        
        .summary-item .value {{
            font-size: 28px;
            font-weight: bold;
            color: #e74c3c;
        }}
        
        .summary-item .label {{
            font-size: 12px;
            color: #7f8c8d;
        }}
        
        .script-output {{
            background: #2c3e50;
            color: #ecf0f1;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 300px;
            overflow-y: auto;
            margin-top: 10px;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #7f8c8d;
        }}
        
        .empty-state svg {{
            width: 80px;
            height: 80px;
            margin-bottom: 20px;
            opacity: 0.5;
        }}
        
        .filter-bar {{
            display: flex;
            gap: 10px;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        
        .filter-btn {{
            padding: 8px 16px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 20px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }}
        
        .filter-btn.active {{
            background: #667eea;
            color: white;
            border-color: #667eea;
        }}
        
        @media (max-width: 768px) {{
            .video-item {{ flex-direction: column; align-items: flex-start; }}
            .video-thumb {{ width: 100%; height: 200px; margin-bottom: 10px; }}
            .video-actions {{ margin-top: 10px; }}
            .toolbar {{ flex-direction: column; align-items: stretch; }}
            .search-box {{ width: 100%; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎬 VideoDedup 重复视频报告</h1>
        <div class="meta">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        <div class="stats">
            <div class="stat-card">
                <span class="number">{total_groups}</span>
                <span class="label">重复组</span>
            </div>
            <div class="stat-card">
                <span class="number">{total_videos}</span>
                <span class="label">重复视频</span>
            </div>
            <div class="stat-card">
                <span class="number">{self._format_size(total_savings)}</span>
                <span class="label">可释放空间</span>
            </div>
        </div>
    </div>
    
    <div class="toolbar">
        <button class="btn btn-secondary" onclick="selectAll()">✓ 全选</button>
        <button class="btn btn-secondary" onclick="deselectAll()">✗ 取消全选</button>
        <button class="btn btn-secondary" onclick="selectDuplicates()">🗑️ 只选重复</button>
        <span style="color: #666;">|</span>
        <button class="btn btn-danger" onclick="generateDeleteScript()">📝 生成删除脚本</button>
        <button class="btn btn-primary" onclick="generateRenameScript()">🏷️ 生成重命名脚本</button>
        <div style="flex: 1;"></div>
        <input type="text" class="search-box" id="searchBox" placeholder="🔍 搜索文件名..." onkeyup="filterVideos()">
    </div>
    
    <div class="container">
        <div class="filter-bar">
            <span style="color: #666; font-size: 14px;">筛选:</span>
            <button class="filter-btn active" onclick="filterType('all')">全部</button>
            <button class="filter-btn" onclick="filterType('identical')">完全相同</button>
            <button class="filter-btn" onclick="filterType('similar')">相似视频</button>
            <button class="filter-btn" onclick="filterType('different-version')">不同版本</button>
        </div>
        
        <div id="groups-container">
"""
        
        # 添加每个组
        for i, group in enumerate(groups, 1):
            html += self._build_group_html(i, group)
        
        # 底部选中摘要
        html += f"""
        </div>
        
        <div class="selected-summary" id="selectedSummary" style="display: none;">
            <h3>📋 已选择的项目</h3>
            <div class="summary-stats">
                <div class="summary-item">
                    <div class="value" id="selectedCount">0</div>
                    <div class="label">选中文件</div>
                </div>
                <div class="summary-item">
                    <div class="value" id="selectedSize">0 MB</div>
                    <div class="label">可释放空间</div>
                </div>
            </div>
            <button class="btn btn-danger" onclick="generateDeleteScript()">生成删除脚本</button>
            <pre class="script-output" id="scriptOutput"></pre>
        </div>
    </div>
    
    <script>
        // 所有视频数据
        const videosData = {json.dumps(self._prepare_js_data(groups))};
        
        // 当前筛选
        let currentFilter = 'all';
        
        // 更新选中统计
        function updateSelection() {{
            const checkboxes = document.querySelectorAll('.video-checkbox input:checked');
            const count = checkboxes.length;
            let size = 0;
            
            checkboxes.forEach(cb => {{
                const sizeVal = parseInt(cb.dataset.size);
                size += sizeVal;
            }});
            
            document.getElementById('selectedCount').textContent = count;
            document.getElementById('selectedSize').textContent = formatSize(size);
            
            const summary = document.getElementById('selectedSummary');
            summary.style.display = count > 0 ? 'block' : 'none';
        }}
        
        // 格式化大小
        function formatSize(bytes) {{
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }}
        
        // 全选
        function selectAll() {{
            document.querySelectorAll('.video-checkbox input:visible').forEach(cb => {{
                cb.checked = true;
            }});
            updateSelection();
        }}
        
        // 取消全选
        function deselectAll() {{
            document.querySelectorAll('.video-checkbox input').forEach(cb => cb.checked = false);
            updateSelection();
        }}
        
        // 只选重复（每组保留第一个）
        function selectDuplicates() {{
            deselectAll();
            document.querySelectorAll('.group').forEach(group => {{
                const checkboxes = group.querySelectorAll('.video-checkbox input');
                checkboxes.forEach((cb, idx) => {{
                    if (idx > 0) cb.checked = true;
                }});
            }});
            updateSelection();
        }}
        
        // 生成删除脚本
        function generateDeleteScript() {{
            const selected = document.querySelectorAll('.video-checkbox input:checked');
            if (selected.length === 0) {{
                alert('请先选择要删除的文件');
                return;
            }}
            
            let script = '#!/bin/bash\\n# VideoDedup 删除脚本\\n# 生成时间: ' + new Date().toLocaleString() + '\\n\\n';
            script += 'echo "准备删除以下 ' + selected.length + ' 个文件:"\\n';
            
            selected.forEach(cb => {{
                const path = cb.dataset.path;
                script += 'echo "  - ' + path + '"\\n';
            }});
            
            script += '\\necho ""\\n';
            script += 'read -p "确定要删除吗? (yes/no): " confirm\\n';
            script += 'if [ "$confirm" = "yes" ]; then\\n';
            
            selected.forEach(cb => {{
                const path = cb.dataset.path;
                script += '    rm -f "' + path + '"\\n';
            }});
            
            script += '    echo "删除完成"\\n';
            script += 'else\\n';
            script += '    echo "已取消"\\n';
            script += 'fi\\n';
            
            document.getElementById('scriptOutput').textContent = script;
            
            // 下载脚本
            const blob = new Blob([script], {{ type: 'text/plain' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'delete_duplicates.sh';
            a.click();
        }}
        
        // 生成重命名脚本
        function generateRenameScript() {{
            const selected = document.querySelectorAll('.video-checkbox input:checked');
            if (selected.length === 0) {{
                alert('请先选择要重命名的文件');
                return;
            }}
            
            let script = '#!/bin/bash\\n# VideoDedup 重命名脚本\\n\\n';
            
            const groups = {{}};
            selected.forEach(cb => {{
                const groupId = cb.dataset.group;
                if (!groups[groupId]) groups[groupId] = [];
                groups[groupId].push(cb.dataset.path);
            }});
            
            Object.keys(groups).forEach(groupId => {{
                groups[groupId].forEach(path => {{
                    const ext = path.split('.').pop();
                    const base = path.substring(0, path.lastIndexOf('.'));
                    const newPath = base + '_dup' + groupId.padStart(3, '0') + '.' + ext;
                    script += 'mv -n "' + path + '" "' + newPath + '"\\n';
                }});
            }});
            
            document.getElementById('scriptOutput').textContent = script;
            
            const blob = new Blob([script], {{ type: 'text/plain' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'rename_duplicates.sh';
            a.click();
        }}
        
        // 搜索过滤
        function filterVideos() {{
            const query = document.getElementById('searchBox').value.toLowerCase();
            document.querySelectorAll('.video-item').forEach(item => {{
                const name = item.dataset.name.toLowerCase();
                item.style.display = name.includes(query) ? 'flex' : 'none';
            }});
        }}
        
        // 类型筛选
        function filterType(type) {{
            currentFilter = type;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            document.querySelectorAll('.group').forEach(group => {{
                if (type === 'all') {{
                    group.style.display = 'block';
                }} else {{
                    const groupType = group.dataset.type;
                    group.style.display = groupType === type ? 'block' : 'none';
                }}
            }});
        }}
        
        // 在文件夹中显示
        function showInFolder(path) {{
            alert('文件位置: ' + path);
        }}
        
        // 初始化
        document.querySelectorAll('.video-checkbox input').forEach(cb => {{
            cb.addEventListener('change', updateSelection);
        }});
    </script>
</body>
</html>"""
        
        return html
    
    def _build_group_html(self, group_id: int, group: Dict) -> str:
        """构建单个组的HTML"""
        videos = group['videos']
        
        # 按大小排序，最大的放前面
        videos_sorted = sorted(videos, key=lambda x: x['size'], reverse=True)
        
        sim_type = group.get('similarity_type', 'similar')
        type_names = {
            'identical': '完全相同',
            'similar': '相似视频',
            'different_version': '不同版本',
            'different_editing': '不同剪辑',
            'maybe': '可能相关'
        }
        type_name = type_names.get(sim_type, sim_type)
        
        html = f'''
        <div class="group" data-type="{sim_type}">
            <div class="group-header">
                <div>
                    <div class="group-title">
                        <span class="group-number">{group_id}</span>
                        <span style="font-weight: 600;">重复组 #{group_id}</span>
                        <span class="group-badge badge-{sim_type}">{type_name}</span>
                    </div>
                    <div class="group-info">
                        原因: {group.get('reason', '未知')} | 视频数量: {len(videos)}
                    </div>
                </div>
            </div>
            <div class="video-list">
'''
        
        for i, video in enumerate(videos_sorted):
            is_first = (i == 0)
            thumb_path = self.generate_thumbnail(video['path'])
            
            size_mb = video['size'] / (1024 * 1024)
            duration_str = f"{video['duration']:.1f}s" if video['duration'] > 0 else "未知"
            resolution = f"{video['width']}x{video['height']}" if video['width'] > 0 else "未知"
            
            html += f'''
                <div class="video-item" data-name="{Path(video['path']).name}">
                    <div class="video-checkbox">
                        <input type="checkbox" 
                               data-path="{video['path']}"
                               data-size="{video['size']}"
                               data-group="{group_id}"
                               {"" if is_first else "checked"}>
                    </div>
                    <div class="video-thumb">
                        {f'<img src="{thumb_path}" alt="缩略图">' if thumb_path else '<div class="no-thumb">无预览</div>'}
                    </div>
                    <div class="video-info">
                        <div class="video-name">{Path(video['path']).name}</div>
                        <div class="video-path">{video['path']}</div>
                        <div class="video-meta">
                            <span class="meta-size">💾 {size_mb:.1f} MB</span>
                            <span class="meta-duration">⏱️ {duration_str}</span>
                            <span class="meta-resolution">📐 {resolution}</span>
                        </div>
                    </div>
                    <div class="video-actions">
                        {"<span class='keep-badge'>建议保留</span>" if is_first else "<span class='delete-badge'>可删除</span>"}
                        <button class="action-btn" onclick="showInFolder('{video['path']}')">📁 打开位置</button>
                    </div>
                </div>
'''
        
        html += '''
            </div>
        </div>
'''
        return html
    
    def _format_size(self, bytes_val: int) -> str:
        """格式化大小"""
        if bytes_val == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} PB"
    
    def _prepare_js_data(self, groups: List[Dict]) -> List[Dict]:
        """为JavaScript准备数据"""
        return groups
    
    def cleanup(self):
        """清理临时文件"""
        if hasattr(self, 'output_dir') and os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)


# 集成到VideoDedup主程序的方法
def export_html_report(groups, output_path: str = "report.html"):
    """
    导出HTML可视化报告
    
    Args:
        groups: 重复组列表
        output_path: 输出HTML文件路径
    """
    generator = HTMLReportGenerator()
    
    # 转换groups为字典格式
    groups_data = []
    for g in groups:
        groups_data.append({
            'group_id': g.group_id,
            'similarity_type': g.similarity_type,
            'reason': g.reason,
            'videos': [v.to_dict() for v in g.videos]
        })
    
    html_file = generator.generate_html(groups_data, output_path)
    
    # 复制缩略图到输出目录
    output_dir = Path(output_path).parent
    if output_dir != Path(generator.output_dir):
        thumb_dest = output_dir / "thumbnails"
        if thumb_dest.exists():
            shutil.rmtree(thumb_dest)
        shutil.copytree(generator.thumbnail_dir, thumb_dest)
        
        # 更新HTML中的路径
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace('thumbnails/', './thumbnails/')
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(content)
    
    print(f"\n可视化报告已生成: {html_file}")
    print(f"请在浏览器中打开查看")
    
    return html_file


if __name__ == '__main__':
    # 测试
    test_groups = [
        {
            'group_id': 1,
            'similarity_type': 'identical',
            'reason': 'identical_quick_hash',
            'videos': [
                {'path': '/test/video1.mp4', 'size': 1000000, 'duration': 120, 'width': 1920, 'height': 1080},
                {'path': '/test/video2.mp4', 'size': 500000, 'duration': 120, 'width': 1280, 'height': 720},
            ]
        }
    ]
    
    generator = HTMLReportGenerator()
    html_file = generator.generate_html(test_groups, "test_report.html")
    print(f"测试报告已生成: {html_file}")
