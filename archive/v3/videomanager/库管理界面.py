#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频管家 - Web可视化界面
功能：库管理可视化面板
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request
from pathlib import Path
import json

from 库管理 import 库管理器, 视频库, 智能分类检测器

app = Flask(__name__)
管理器 = 库管理器()

# ============ HTML模板 ============
HTML模板 = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>视频管家 - 库管理面板</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        /* 头部 */
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        
        .header p {
            opacity: 0.9;
            font-size: 1.1rem;
        }
        
        /* 统计卡片 */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 50px rgba(0,0,0,0.15);
        }
        
        .stat-card .icon {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .stat-card .number {
            font-size: 2rem;
            font-weight: bold;
            color: #333;
        }
        
        .stat-card .label {
            color: #666;
            font-size: 0.9rem;
            margin-top: 5px;
        }
        
        .stat-card.uncategorized { border-top: 4px solid #f59e0b; }
        .stat-card.classifying { border-top: 4px solid #3b82f6; }
        .stat-card.classified { border-top: 4px solid #10b981; }
        .stat-card.total { border-top: 4px solid #8b5cf6; }
        
        /* 操作栏 */
        .toolbar {
            background: white;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        .btn-secondary {
            background: #f3f4f6;
            color: #374151;
        }
        
        .btn-secondary:hover {
            background: #e5e7eb;
        }
        
        .filter-group {
            display: flex;
            gap: 10px;
            margin-left: auto;
        }
        
        .filter-btn {
            padding: 8px 16px;
            border: 2px solid #e5e7eb;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .filter-btn:hover, .filter-btn.active {
            border-color: #667eea;
            color: #667eea;
        }
        
        /* 库卡片网格 */
        .library-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }
        
        .library-card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        
        .library-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 50px rgba(0,0,0,0.15);
        }
        
        .library-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
        }
        
        .library-card.uncategorized::before { background: #f59e0b; }
        .library-card.classifying::before { background: #3b82f6; }
        .library-card.classified::before { background: #10b981; }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 15px;
        }
        
        .card-title {
            font-size: 1.3rem;
            font-weight: 600;
            color: #1f2937;
            word-break: break-all;
        }
        
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
            white-space: nowrap;
        }
        
        .status-uncategorized {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-classifying {
            background: #dbeafe;
            color: #1e40af;
        }
        
        .status-classified {
            background: #d1fae5;
            color: #065f46;
        }
        
        .card-path {
            color: #6b7280;
            font-size: 0.85rem;
            margin-bottom: 15px;
            word-break: break-all;
        }
        
        .card-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 15px;
            padding: 15px;
            background: #f9fafb;
            border-radius: 10px;
        }
        
        .card-stat {
            text-align: center;
        }
        
        .card-stat .value {
            font-size: 1.3rem;
            font-weight: bold;
            color: #374151;
        }
        
        .card-stat .label {
            font-size: 0.75rem;
            color: #9ca3af;
            margin-top: 3px;
        }
        
        .card-people {
            margin-bottom: 15px;
        }
        
        .people-label {
            font-size: 0.85rem;
            color: #6b7280;
            margin-bottom: 8px;
        }
        
        .people-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        
        .people-tag {
            background: #ede9fe;
            color: #5b21b6;
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.85rem;
        }
        
        .people-tag.empty {
            background: #f3f4f6;
            color: #9ca3af;
            font-style: italic;
        }
        
        .card-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .card-btn {
            flex: 1;
            min-width: 80px;
            padding: 10px;
            border: 1px solid #e5e7eb;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.3s;
        }
        
        .card-btn:hover {
            background: #f9fafb;
            border-color: #d1d5db;
        }
        
        /* 空状态 */
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: white;
        }
        
        .empty-state .icon {
            font-size: 5rem;
            margin-bottom: 20px;
            opacity: 0.8;
        }
        
        .empty-state h2 {
            font-size: 1.5rem;
            margin-bottom: 10px;
        }
        
        .empty-state p {
            opacity: 0.8;
        }
        
        /* 模态框 */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: white;
            border-radius: 20px;
            padding: 30px;
            width: 90%;
            max-width: 500px;
            max-height: 90vh;
            overflow-y: auto;
        }
        
        .modal-header {
            margin-bottom: 20px;
        }
        
        .modal-header h2 {
            color: #1f2937;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #374151;
            font-weight: 500;
        }
        
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e5e7eb;
            border-radius: 10px;
            font-size: 1rem;
            transition: border-color 0.3s;
        }
        
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .status-options {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .status-option {
            flex: 1;
            min-width: 100px;
            padding: 12px;
            border: 2px solid #e5e7eb;
            border-radius: 10px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .status-option:hover {
            border-color: #d1d5db;
        }
        
        .status-option.selected {
            border-color: #667eea;
            background: #ede9fe;
        }
        
        .modal-actions {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            margin-top: 20px;
        }
        
        /* 加载动画 */
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* 响应式 */
        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8rem;
            }
            
            .library-grid {
                grid-template-columns: 1fr;
            }
            
            .toolbar {
                flex-direction: column;
                align-items: stretch;
            }
            
            .filter-group {
                margin-left: 0;
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部 -->
        <div class="header">
            <h1>📹 视频管家</h1>
            <p>视频库管理与分类可视化面板</p>
        </div>
        
        <!-- 统计卡片 -->
        <div class="stats-grid" id="statsGrid">
            <!-- 动态生成 -->
        </div>
        
        <!-- 操作栏 -->
        <div class="toolbar">
            <button class="btn btn-primary" onclick="openAddModal()">
                <span>➕</span> 添加库
            </button>
            <button class="btn btn-secondary" onclick="refreshData()">
                <span>🔄</span> 刷新
            </button>
            <div class="filter-group">
                <button class="filter-btn active" onclick="filterLibraries('all')">全部</button>
                <button class="filter-btn" onclick="filterLibraries('未分类')">未分类</button>
                <button class="filter-btn" onclick="filterLibraries('分类中')">分类中</button>
                <button class="filter-btn" onclick="filterLibraries('已分类')">已分类</button>
            </div>
        </div>
        
        <!-- 库卡片网格 -->
        <div class="library-grid" id="libraryGrid">
            <!-- 动态生成 -->
        </div>
        
        <!-- 空状态 -->
        <div class="empty-state" id="emptyState" style="display: none;">
            <div class="icon">📦</div>
            <h2>暂无视频库</h2>
            <p>点击"添加库"按钮开始管理您的视频</p>
        </div>
    </div>
    
    <!-- 添加库模态框 -->
    <div class="modal" id="addModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>➕ 添加视频库</h2>
            </div>
            <div class="form-group">
                <label>文件夹路径</label>
                <input type="text" id="libraryPath" placeholder="例如: /home/user/视频/张三">
            </div>
            <div class="form-group">
                <label>分类状态</label>
                <div class="status-options">
                    <div class="status-option" data-status="未分类" onclick="selectStatus(this)">
                        📦 未分类
                    </div>
                    <div class="status-option" data-status="分类中" onclick="selectStatus(this)">
                        ⏳ 分类中
                    </div>
                    <div class="status-option" data-status="已分类" onclick="selectStatus(this)">
                        ✅ 已分类
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label>关联人物（可选，用逗号分隔）</label>
                <input type="text" id="libraryPeople" placeholder="例如: 张三, 李四">
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeModal('addModal')">取消</button>
                <button class="btn btn-primary" onclick="addLibrary()">添加</button>
            </div>
        </div>
    </div>
    
    <!-- 编辑库模态框 -->
    <div class="modal" id="editModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>✏️ 编辑库</h2>
            </div>
            <input type="hidden" id="editLibraryPath">
            <div class="form-group">
                <label>分类状态</label>
                <div class="status-options" id="editStatusOptions">
                    <div class="status-option" data-status="未分类" onclick="selectEditStatus(this)">
                        📦 未分类
                    </div>
                    <div class="status-option" data-status="分类中" onclick="selectEditStatus(this)">
                        ⏳ 分类中
                    </div>
                    <div class="status-option" data-status="已分类" onclick="selectEditStatus(this)">
                        ✅ 已分类
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label>关联人物（用逗号分隔）</label>
                <input type="text" id="editLibraryPeople">
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeModal('editModal')">取消</button>
                <button class="btn btn-primary" onclick="saveLibrary()">保存</button>
            </div>
        </div>
    </div>
    
    <script>
        let libraries = [];
        let currentFilter = 'all';
        let selectedStatus = '未分类';
        let selectedEditStatus = '';
        
        // 初始化
        document.addEventListener('DOMContentLoaded', function() {
            refreshData();
        });
        
        // 刷新数据
        async function refreshData() {
            try {
                const [libsRes, statsRes] = await Promise.all([
                    fetch('/api/libraries'),
                    fetch('/api/stats')
                ]);
                
                libraries = await libsRes.json();
                const stats = await statsRes.json();
                
                renderStats(stats);
                renderLibraries();
            } catch (error) {
                console.error('获取数据失败:', error);
                alert('获取数据失败，请检查后端服务');
            }
        }
        
        // 渲染统计
        function renderStats(stats) {
            const html = `
                <div class="stat-card uncategorized">
                    <div class="icon">📦</div>
                    <div class="number">${stats.uncategorized}</div>
                    <div class="label">未分类</div>
                </div>
                <div class="stat-card classifying">
                    <div class="icon">⏳</div>
                    <div class="number">${stats.classifying}</div>
                    <div class="label">分类中</div>
                </div>
                <div class="stat-card classified">
                    <div class="icon">✅</div>
                    <div class="number">${stats.classified}</div>
                    <div class="label">已分类</div>
                </div>
                <div class="stat-card total">
                    <div class="icon">📁</div>
                    <div class="number">${stats.total}</div>
                    <div class="label">库总数</div>
                </div>
            `;
            document.getElementById('statsGrid').innerHTML = html;
        }
        
        // 渲染库列表
        function renderLibraries() {
            const grid = document.getElementById('libraryGrid');
            const emptyState = document.getElementById('emptyState');
            
            let filtered = libraries;
            if (currentFilter !== 'all') {
                filtered = libraries.filter(lib => lib.status === currentFilter);
            }
            
            if (filtered.length === 0) {
                grid.style.display = 'none';
                emptyState.style.display = 'block';
                return;
            }
            
            grid.style.display = 'grid';
            emptyState.style.display = 'none';
            
            grid.innerHTML = filtered.map(lib => `
                <div class="library-card ${getStatusClass(lib.status)}">
                    <div class="card-header">
                        <div class="card-title">${lib.name}</div>
                        <span class="status-badge status-${getStatusClass(lib.status)}">${lib.status}</span>
                    </div>
                    <div class="card-path">${lib.path}</div>
                    <div class="card-stats">
                        <div class="card-stat">
                            <div class="value">${lib.video_count || 0}</div>
                            <div class="label">视频</div>
                        </div>
                        <div class="card-stat">
                            <div class="value">${formatSize(lib.total_size)}</div>
                            <div class="label">大小</div>
                        </div>
                        <div class="card-stat">
                            <div class="value">${formatDuration(lib.total_duration)}</div>
                            <div class="label">时长</div>
                        </div>
                    </div>
                    <div class="card-people">
                        <div class="people-label">关联人物</div>
                        <div class="people-tags">
                            ${lib.people.length > 0 
                                ? lib.people.map(p => `<span class="people-tag">${p}</span>`).join('')
                                : '<span class="people-tag empty">未设置</span>'
                            }
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="card-btn" onclick="editLibrary('${lib.path}')">✏️ 编辑</button>
                        <button class="card-btn" onclick="detectLibrary('${lib.path}')">🔍 检测</button>
                        <button class="card-btn" onclick="deleteLibrary('${lib.path}')">🗑️ 删除</button>
                    </div>
                </div>
            `).join('');
        }
        
        // 获取状态类名
        function getStatusClass(status) {
            return {
                '未分类': 'uncategorized',
                '分类中': 'classifying',
                '已分类': 'classified'
            }[status] || 'uncategorized';
        }
        
        // 格式化大小
        function formatSize(bytes) {
            if (!bytes) return '0 B';
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            let i = 0;
            while (bytes >= 1024 && i < units.length - 1) {
                bytes /= 1024;
                i++;
            }
            return bytes.toFixed(1) + ' ' + units[i];
        }
        
        // 格式化时长
        function formatDuration(seconds) {
            if (!seconds) return '0h';
            const hours = Math.floor(seconds / 3600);
            if (hours < 1) return Math.floor(seconds / 60) + 'm';
            return hours + 'h';
        }
        
        // 筛选库
        function filterLibraries(filter) {
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.toggle('active', 
                    (filter === 'all' && btn.textContent === '全部') ||
                    btn.textContent.includes(filter)
                );
            });
            renderLibraries();
        }
        
        // 模态框操作
        function openAddModal() {
            document.getElementById('addModal').classList.add('active');
            document.getElementById('libraryPath').value = '';
            document.getElementById('libraryPeople').value = '';
            selectStatus(document.querySelector('[data-status="未分类"]'));
        }
        
        function closeModal(id) {
            document.getElementById(id).classList.remove('active');
        }
        
        function selectStatus(el) {
            document.querySelectorAll('#addModal .status-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            el.classList.add('selected');
            selectedStatus = el.dataset.status;
        }
        
        function selectEditStatus(el) {
            document.querySelectorAll('#editModal .status-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            el.classList.add('selected');
            selectedEditStatus = el.dataset.status;
        }
        
        // 添加库
        async function addLibrary() {
            const path = document.getElementById('libraryPath').value.trim();
            const people = document.getElementById('libraryPeople').value
                .split(',').map(p => p.trim()).filter(p => p);
            
            if (!path) {
                alert('请输入文件夹路径');
                return;
            }
            
            try {
                const res = await fetch('/api/libraries', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path, status: selectedStatus, people })
                });
                
                const data = await res.json();
                if (data.success) {
                    closeModal('addModal');
                    refreshData();
                } else {
                    alert(data.error || '添加失败');
                }
            } catch (error) {
                alert('添加失败: ' + error.message);
            }
        }
        
        // 编辑库
        function editLibrary(path) {
            const lib = libraries.find(l => l.path === path);
            if (!lib) return;
            
            document.getElementById('editLibraryPath').value = path;
            document.getElementById('editLibraryPeople').value = lib.people.join(', ');
            
            // 选中当前状态
            document.querySelectorAll('#editModal .status-option').forEach(opt => {
                opt.classList.toggle('selected', opt.dataset.status === lib.status);
            });
            selectedEditStatus = lib.status;
            
            document.getElementById('editModal').classList.add('active');
        }
        
        // 保存库
        async function saveLibrary() {
            const path = document.getElementById('editLibraryPath').value;
            const people = document.getElementById('editLibraryPeople').value
                .split(',').map(p => p.trim()).filter(p => p);
            
            try {
                const res = await fetch(`/api/libraries/${encodeURIComponent(path)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        status: selectedEditStatus || '未分类', 
                        people 
                    })
                });
                
                const data = await res.json();
                if (data.success) {
                    closeModal('editModal');
                    refreshData();
                } else {
                    alert(data.error || '保存失败');
                }
            } catch (error) {
                alert('保存失败: ' + error.message);
            }
        }
        
        // 删除库
        async function deleteLibrary(path) {
            if (!confirm('确定要删除这个库吗？\n注意：只会删除记录，不会删除实际文件')) {
                return;
            }
            
            try {
                const res = await fetch(`/api/libraries/${encodeURIComponent(path)}`, {
                    method: 'DELETE'
                });
                
                const data = await res.json();
                if (data.success) {
                    refreshData();
                } else {
                    alert(data.error || '删除失败');
                }
            } catch (error) {
                alert('删除失败: ' + error.message);
            }
        }
        
        // 检测库
        async function detectLibrary(path) {
            try {
                const res = await fetch(`/api/libraries/${encodeURIComponent(path)}/detect`, {
                    method: 'POST'
                });
                
                const data = await res.json();
                if (data.success) {
                    alert(`检测完成！\n分类类型: ${data.result.classification_type}\n置信度: ${(data.result.confidence * 100).toFixed(0)}%\n建议: ${data.result.suggestion}`);
                    refreshData();
                } else {
                    alert(data.error || '检测失败');
                }
            } catch (error) {
                alert('检测失败: ' + error.message);
            }
        }
        
        // 点击模态框外部关闭
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', function(e) {
                if (e.target === this) {
                    this.classList.remove('active');
                }
            });
        });
    </script>
</body>
</html>
'''


# ============ API路由 ============

@app.route('/')
def 首页():
    """返回Web界面"""
    return HTML模板


@app.route('/api/libraries', methods=['GET'])
def 获取库列表():
    """获取所有库"""
    库列表 = 管理器.获取库列表()
    return jsonify([{
        'path': 库.路径,
        'name': 库.名称,
        'status': 库.分类状态,
        'people': 库.关联人物,
        'video_count': 库.视频数量,
        'total_size': 库.总大小,
        'total_duration': 库.总时长,
        'last_scan': 库.最后扫描时间,
        'remark': 库.备注
    } for 库 in 库列表])


@app.route('/api/libraries', methods=['POST'])
def 添加库():
    """添加新库"""
    数据 = request.json
    路径 = 数据.get('path', '').strip()
    状态 = 数据.get('status', '未分类')
    人物 = 数据.get('people', [])
    
    if not 路径:
        return jsonify({'success': False, 'error': '路径不能为空'})
    
    if not os.path.exists(路径):
        return jsonify({'success': False, 'error': '路径不存在'})
    
    # 先进行检测
    结果 = 智能分类检测器.检测并标记库(路径, 自动标记=False)
    
    if '错误' in 结果:
        return jsonify({'success': False, 'error': 结果['错误']})
    
    库 = 结果['库信息']
    库.分类状态 = 状态
    库.关联人物 = 人物
    
    with 库管理数据库() as db:
        if db.添加库(库):
            return jsonify({'success': True, 'library': {
                'path': 库.路径,
                'name': 库.名称,
                'status': 库.分类状态
            }})
        else:
            return jsonify({'success': False, 'error': '添加失败'})


@app.route('/api/libraries/<path:库路径>', methods=['PUT'])
def 更新库(库路径):
    """更新库信息"""
    数据 = request.json
    状态 = 数据.get('status')
    人物 = 数据.get('people', [])
    
    成功 = True
    with 库管理数据库() as db:
        if 状态:
            成功 = 成功 and db.更新库状态(库路径, 状态)
        if 人物 is not None:
            成功 = 成功 and db.更新库人物(库路径, 人物)
    
    return jsonify({'success': 成功})


@app.route('/api/libraries/<path:库路径>', methods=['DELETE'])
def 删除库(库路径):
    """删除库"""
    if 管理器.删除库(库路径):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@app.route('/api/libraries/<path:库路径>/detect', methods=['POST'])
def 检测库(库路径):
    """检测库的分类状态"""
    结果 = 管理器.重新检测库(库路径)
    
    if '错误' in 结果:
        return jsonify({'success': False, 'error': 结果['错误']})
    
    分析 = 结果['分析结果']
    return jsonify({
        'success': True,
        'result': {
            'classification_type': 分析['分类类型'],
            'confidence': 分析['置信度'],
            'video_distribution': 分析['视频分布'],
            'suggestion': 分析['建议']
        }
    })


@app.route('/api/stats', methods=['GET'])
def 获取统计():
    """获取统计信息"""
    统计 = 管理器.获取统计()
    return jsonify({
        'total': 统计['库总数'],
        'uncategorized': 统计['未分类'],
        'classifying': 统计['分类中'],
        'classified': 统计['已分类'],
        'total_videos': 统计['总视频数'],
        'total_size_gb': round(统计['总大小GB'], 2),
        'total_duration_hours': round(统计['总时长小时'], 1)
    })


# 启动服务
if __name__ == '__main__':
    print("="*60)
    print("🎬 视频管家 - Web可视化界面")
    print("="*60)
    print("启动中...")
    print("")
    print("访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
