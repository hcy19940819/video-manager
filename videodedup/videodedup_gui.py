#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoDedup GUI - 视频去重图形界面
使用 tkinter，支持拖放、进度显示、结果预览
"""

import os
import sys
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Callable
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# 导入核心模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from videodedup import (
    VideoDedup, FingerprintDB, VideoFingerprint, 
    SimilarityCalculator, DuplicateGroup, VIDEO_EXTENSIONS
)


class VideoPreviewDialog(tk.Toplevel):
    """视频预览对话框"""
    
    def __init__(self, parent, video_path: str):
        super().__init__(parent)
        self.title("视频信息")
        self.geometry("500x400")
        self.transient(parent)
        
        # 获取视频信息
        info_frame = ttk.LabelFrame(self, text="文件信息", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        path = Path(video_path)
        info_text = f"""
文件名: {path.name}
路径: {path.parent}
大小: {path.stat().st_size / (1024**2):.2f} MB
修改时间: {datetime.fromtimestamp(path.stat().st_mtime)}
        """
        
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # 尝试获取视频信息
        try:
            import cv2
            cap = cv2.VideoCapture(str(path))
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = total_frames / fps if fps > 0 else 0
                
                video_info = f"""
分辨率: {width}x{height}
帧率: {fps:.2f} fps
总帧数: {total_frames}
时长: {duration:.1f} 秒 ({int(duration//60)}:{int(duration%60):02d})
                """
                ttk.Label(info_frame, text=video_info, justify=tk.LEFT).pack(anchor=tk.W)
                cap.release()
        except Exception as e:
            ttk.Label(info_frame, text=f"无法获取视频信息: {e}").pack(anchor=tk.W)
        
        # 操作按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(btn_frame, text="在文件夹中显示", 
                  command=lambda: self.open_in_folder(path)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="播放视频", 
                  command=lambda: self.play_video(path)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", 
                  command=self.destroy).pack(side=tk.RIGHT, padx=5)
    
    def open_in_folder(self, path: Path):
        """在文件夹中显示"""
        import subprocess
        if sys.platform == 'win32':
            subprocess.run(['explorer', '/select,', str(path)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', '-R', str(path)])
        else:
            subprocess.run(['xdg-open', str(path.parent)])
    
    def play_video(self, path: Path):
        """播放视频"""
        import subprocess
        if sys.platform == 'win32':
            os.startfile(str(path))
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(path)])
        else:
            subprocess.run(['xdg-open', str(path)])


class DuplicateItemFrame(ttk.Frame):
    """重复组展示框架"""
    
    def __init__(self, parent, group: DuplicateGroup, on_action: Callable):
        super().__init__(parent, relief=tk.GROOVE, padding=5)
        self.group = group
        self.on_action = on_action
        self.check_vars = []
        
        # 组标题
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=2)
        
        sim_type = "完全相同" if group.similarity_type == 'identical' else "相似视频"
        ttk.Label(header, text=f"组 #{group.group_id} - {sim_type}", 
                 font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        
        ttk.Label(header, text=f"原因: {group.reason}", 
                 foreground='gray').pack(side=tk.RIGHT)
        
        # 视频列表
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 按大小排序，最大的在前面（建议保留）
        sorted_videos = sorted(group.videos, key=lambda x: x.size, reverse=True)
        
        for i, video in enumerate(sorted_videos):
            row = ttk.Frame(list_frame)
            row.pack(fill=tk.X, pady=1)
            
            # 复选框
            var = tk.BooleanVar(value=(i > 0))  # 默认选中非第一个
            chk = ttk.Checkbutton(row, variable=var)
            chk.pack(side=tk.LEFT)
            self.check_vars.append((var, video))
            
            # 保留标记
            if i == 0:
                ttk.Label(row, text="[建议保留]", foreground='green', 
                         font=('Arial', 8)).pack(side=tk.LEFT, padx=5)
            else:
                ttk.Label(row, text="[可删除]", foreground='red',
                         font=('Arial', 8)).pack(side=tk.LEFT, padx=5)
            
            # 文件信息
            size_mb = video.size / (1024*1024)
            duration_str = f"{video.duration:.0f}s" if video.duration > 0 else "未知"
            resolution = f"{video.width}x{video.height}" if video.width > 0 else "未知"
            
            info_text = f"{Path(video.path).name[:40]} | {size_mb:.1f}MB | {duration_str} | {resolution}"
            lbl = ttk.Label(row, text=info_text, cursor="hand2")
            lbl.pack(side=tk.LEFT, padx=5)
            lbl.bind("<Button-1>", lambda e, v=video: self.show_preview(v))
        
        # 操作按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="删除选中", 
                  command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="移动到...",
                  command=self.move_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="导出信息",
                  command=self.export_info).pack(side=tk.LEFT, padx=5)
    
    def show_preview(self, video: VideoFingerprint):
        """显示视频预览"""
        VideoPreviewDialog(self, video.path)
    
    def delete_selected(self):
        """删除选中的视频"""
        selected = [v for var, v in self.check_vars if var.get()]
        if not selected:
            messagebox.showwarning("提示", "请先选择要删除的视频")
            return
        
        if messagebox.askyesno("确认删除", 
                              f"确定要删除 {len(selected)} 个视频吗？\n此操作不可恢复！"):
            deleted = []
            failed = []
            for v in selected:
                try:
                    os.remove(v.path)
                    deleted.append(v.path)
                except Exception as e:
                    failed.append(f"{v.path}: {e}")
            
            if deleted:
                messagebox.showinfo("删除完成", f"成功删除 {len(deleted)} 个视频")
                self.on_action('refresh')
            if failed:
                messagebox.showerror("删除失败", "\n".join(failed))
    
    def move_selected(self):
        """移动选中的视频"""
        selected = [v for var, v in self.check_vars if var.get()]
        if not selected:
            messagebox.showwarning("提示", "请先选择要移动的视频")
            return
        
        target_dir = filedialog.askdirectory(title="选择目标目录")
        if not target_dir:
            return
        
        moved = []
        failed = []
        for v in selected:
            try:
                src = Path(v.path)
                dst = Path(target_dir) / src.name
                # 处理重名
                counter = 1
                while dst.exists():
                    dst = Path(target_dir) / f"{src.stem}_{counter}{src.suffix}"
                    counter += 1
                src.rename(dst)
                moved.append(str(dst))
            except Exception as e:
                failed.append(f"{v.path}: {e}")
        
        if moved:
            messagebox.showinfo("移动完成", f"成功移动 {len(moved)} 个视频")
            self.on_action('refresh')
        if failed:
            messagebox.showerror("移动失败", "\n".join(failed))
    
    def export_info(self):
        """导出组信息"""
        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"重复组 #{self.group.group_id}\n")
                f.write(f"相似度类型: {self.group.similarity_type}\n")
                f.write(f"原因: {self.group.reason}\n\n")
                f.write("文件列表:\n")
                for v in self.group.videos:
                    f.write(f"  {v.path}\n")
                    f.write(f"    大小: {v.size / (1024**2):.2f} MB\n")
                    f.write(f"    时长: {v.duration:.1f}s\n")
                    f.write(f"    分辨率: {v.width}x{v.height}\n\n")
            messagebox.showinfo("导出完成", f"信息已保存到:\n{filename}")


class VideoDedupGUI:
    """视频去重GUI主类"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("VideoDedup - 视频去重工具")
        self.root.geometry("900x700")
        
        self.dedup = None
        self.duplicate_groups = []
        
        self._create_menu()
        self._create_main_interface()
        
        # 检查依赖
        try:
            import cv2
            self.has_video = True
        except ImportError:
            self.has_video = False
            messagebox.showwarning("警告", 
                "未安装 opencv-python，视频分析功能受限\n"
                "建议运行: pip install opencv-python pillow numpy")
    
    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="选择扫描目录...", command=self.browse_scan_dir)
        file_menu.add_command(label="打开数据库...", command=self.browse_db)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        
        # 工具菜单
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tools_menu)
        tools_menu.add_command(label="清空数据库", command=self.clear_database)
        tools_menu.add_command(label="导出所有指纹", command=self.export_fingerprints)
        
        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用说明", command=self.show_help)
        help_menu.add_command(label="关于", command=self.show_about)
    
    def _create_main_interface(self):
        """创建主界面"""
        # 顶部配置区域
        config_frame = ttk.LabelFrame(self.root, text="配置", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 数据库路径
        db_frame = ttk.Frame(config_frame)
        db_frame.pack(fill=tk.X, pady=2)
        ttk.Label(db_frame, text="数据库:").pack(side=tk.LEFT)
        self.db_var = tk.StringVar(value="videodedup.db")
        ttk.Entry(db_frame, textvariable=self.db_var, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(db_frame, text="浏览...", command=self.browse_db).pack(side=tk.LEFT)
        
        # 扫描路径
        path_frame = ttk.Frame(config_frame)
        path_frame.pack(fill=tk.X, pady=2)
        ttk.Label(path_frame, text="扫描路径:").pack(side=tk.LEFT)
        self.path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self.path_var, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(path_frame, text="浏览...", command=self.browse_scan_dir).pack(side=tk.LEFT)
        
        # 选项
        options_frame = ttk.Frame(config_frame)
        options_frame.pack(fill=tk.X, pady=5)
        
        self.incremental_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="增量扫描", 
                       variable=self.incremental_var).pack(side=tk.LEFT, padx=5)
        
        self.cross_compare_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="跨目录对比",
                       variable=self.cross_compare_var).pack(side=tk.LEFT, padx=5)
        
        self.similarity_var = tk.StringVar(value="standard")
        ttk.Label(options_frame, text="相似度:").pack(side=tk.LEFT, padx=(20, 5))
        ttk.Combobox(options_frame, textvariable=self.similarity_var, 
                    values=["strict", "standard", "loose"], 
                    width=10, state="readonly").pack(side=tk.LEFT)
        
        # 操作按钮
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(btn_frame, text="🔍 开始扫描", 
                  command=self.start_scan).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📋 查找重复", 
                  command=self.find_duplicates).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🏷️ 重命名标记", 
                  command=self.rename_duplicates).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📊 查看统计", 
                  command=self.show_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📁 与外部库对比",
                  command=self.compare_external).pack(side=tk.LEFT, padx=5)
        
        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(self.root, variable=self.progress_var, 
                                       maximum=100, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, 
                 foreground='gray').pack(anchor=tk.W, padx=10)
        
        # 结果区域（带滚动条）
        result_frame = ttk.LabelFrame(self.root, text="结果", padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建画布和滚动条
        self.canvas = tk.Canvas(result_frame)
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", 
                                 command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定鼠标滚轮
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    
    def _on_mousewheel(self, event):
        """鼠标滚轮滚动"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def browse_db(self):
        """选择数据库文件"""
        filename = filedialog.askopenfilename(
            defaultextension=".db",
            filetypes=[("数据库文件", "*.db"), ("所有文件", "*.*")]
        )
        if filename:
            self.db_var.set(filename)
    
    def browse_scan_dir(self):
        """选择扫描目录"""
        directory = filedialog.askdirectory()
        if directory:
            self.path_var.set(directory)
    
    def update_status(self, message: str, progress: Optional[float] = None):
        """更新状态"""
        self.status_var.set(message)
        if progress is not None:
            self.progress_var.set(progress)
        self.root.update_idletasks()
    
    def start_scan(self):
        """开始扫描"""
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("提示", "请先选择扫描路径")
            return
        
        if not os.path.exists(path):
            messagebox.showerror("错误", "路径不存在")
            return
        
        db_path = self.db_var.get() or "videodedup.db"
        
        def scan_task():
            try:
                self.update_status("正在初始化...", 0)
                dedup = VideoDedup(db_path=db_path, workers=4)
                
                self.update_status("正在扫描视频文件...", 10)
                
                # 扫描
                dedup.scan(
                    paths=[path],
                    incremental=self.incremental_var.get(),
                    update_existing=False
                )
                
                self.update_status(f"扫描完成！新文件: {dedup._scan_stats['new']}, "
                                  f"跳过: {dedup._scan_stats['skipped']}", 100)
                
                self.dedup = dedup
                messagebox.showinfo("完成", "扫描完成！")
                
            except Exception as e:
                self.update_status(f"错误: {str(e)}")
                messagebox.showerror("错误", str(e))
        
        # 在后台线程运行
        threading.Thread(target=scan_task, daemon=True).start()
    
    def find_duplicates(self):
        """查找重复"""
        db_path = self.db_var.get() or "videodedup.db"
        
        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "数据库不存在，请先扫描")
            return
        
        def find_task():
            try:
                self.update_status("正在查找重复视频...", 0)
                
                dedup = VideoDedup(db_path=db_path)
                path = self.path_var.get().strip() or None
                paths = [path] if path else None
                
                groups = dedup.find_duplicates(
                    paths=paths,
                    cross_compare=self.cross_compare_var.get()
                )
                
                self.duplicate_groups = groups
                
                # 在主线程更新UI
                self.root.after(0, lambda: self._show_results(groups))
                
            except Exception as e:
                self.update_status(f"错误: {str(e)}")
                messagebox.showerror("错误", str(e))
        
        threading.Thread(target=find_task, daemon=True).start()
    
    def _show_results(self, groups: List[DuplicateGroup]):
        """显示结果"""
        # 清空现有结果
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        if not groups:
            ttk.Label(self.scrollable_frame, text="未发现重复视频", 
                     font=('Arial', 14)).pack(pady=50)
            self.update_status("未发现重复视频", 100)
            return
        
        # 统计可释放空间
        total_savings = 0
        for g in groups:
            sizes = sorted([v.size for v in g.videos], reverse=True)
            total_savings += sum(sizes[1:])
        
        # 汇总信息
        summary = ttk.LabelFrame(self.scrollable_frame, text="汇总", padding=10)
        summary.pack(fill=tk.X, padx=5, pady=5)
        
        info_text = (f"发现 {len(groups)} 组重复视频\n"
                    f"预计可释放空间: {total_savings / (1024**3):.2f} GB")
        ttk.Label(summary, text=info_text, font=('Arial', 11)).pack(anchor=tk.W)
        
        # 每个重复组
        for group in groups:
            item = DuplicateItemFrame(
                self.scrollable_frame, 
                group,
                on_action=self._on_group_action
            )
            item.pack(fill=tk.X, padx=5, pady=5)
        
        self.update_status(f"找到 {len(groups)} 组重复视频", 100)
    
    def _on_group_action(self, action: str):
        """处理组操作回调"""
        if action == 'refresh':
            # 刷新结果
            self.find_duplicates()
    
    def show_stats(self):
        """显示统计"""
        db_path = self.db_var.get() or "videodedup.db"
        
        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "数据库不存在")
            return
        
        try:
            dedup = VideoDedup(db_path=db_path)
            
            # 创建统计窗口
            stats_window = tk.Toplevel(self.root)
            stats_window.title("数据库统计")
            stats_window.geometry("400x300")
            
            with FingerprintDB(db_path) as db:
                fps = db.get_all_fingerprints()
            
            total_size = sum(fp.size for fp in fps)
            total_duration = sum(fp.duration for fp in fps)
            
            info = f"""
数据库路径: {db_path}

视频数量: {len(fps)}
总大小: {total_size / (1024**3):.2f} GB
总时长: {total_duration / 3600:.1f} 小时

分辨率分布:
"""
            # 统计分辨率
            res_counts = {}
            for fp in fps:
                if fp.width > 0 and fp.height > 0:
                    res = f"{fp.width}x{fp.height}"
                    res_counts[res] = res_counts.get(res, 0) + 1
            
            for res, count in sorted(res_counts.items(), 
                                    key=lambda x: x[1], reverse=True)[:5]:
                info += f"  {res}: {count} 个\n"
            
            text = scrolledtext.ScrolledText(stats_window, wrap=tk.WORD, 
                                            font=('Consolas', 10))
            text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text.insert(tk.END, info)
            text.config(state=tk.DISABLED)
            
        except Exception as e:
            messagebox.showerror("错误", str(e))
    
    def compare_external(self):
        """与外部库对比"""
        external_db = filedialog.askopenfilename(
            title="选择外部数据库",
            filetypes=[("数据库文件", "*.db"), ("所有文件", "*.*")]
        )
        
        if not external_db:
            return
        
        db_path = self.db_var.get() or "videodedup.db"
        
        def compare_task():
            try:
                self.update_status("正在跨库对比...", 0)
                
                dedup = VideoDedup(db_path=db_path)
                path = self.path_var.get().strip() or None
                paths = [path] if path else None
                
                groups = dedup.compare_with_external(external_db, paths)
                
                self.duplicate_groups = groups
                self.root.after(0, lambda: self._show_results(groups))
                
            except Exception as e:
                self.update_status(f"错误: {str(e)}")
                messagebox.showerror("错误", str(e))
        
        threading.Thread(target=compare_task, daemon=True).start()
    
    def clear_database(self):
        """清空数据库"""
        db_path = self.db_var.get() or "videodedup.db"
        
        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "数据库不存在")
            return
        
        if messagebox.askyesno("确认", "确定要清空数据库吗？所有指纹将丢失！"):
            try:
                os.remove(db_path)
                messagebox.showinfo("完成", "数据库已清空")
            except Exception as e:
                messagebox.showerror("错误", str(e))
    
    def export_fingerprints(self):
        """导出指纹"""
        db_path = self.db_var.get() or "videodedup.db"
        
        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "数据库不存在")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if filename:
            try:
                with FingerprintDB(db_path) as db:
                    fps = db.get_all_fingerprints()
                
                data = [fp.to_dict() for fp in fps]
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                messagebox.showinfo("完成", f"已导出 {len(fps)} 条指纹")
            except Exception as e:
                messagebox.showerror("错误", str(e))
    
    def show_help(self):
        """显示帮助"""
        help_text = """
VideoDedup 使用说明

1. 扫描视频
   - 选择要扫描的目录
   - 点击"开始扫描"生成指纹
   - 支持增量扫描（只处理新文件）

2. 查找重复
   - 点击"查找重复"
   - 系统会自动比对所有视频
   - 结果按组显示，建议保留最大的

3. 处理重复
   - 勾选要删除或移动的视频
   - 点击相应按钮操作
   - 可以预览视频信息

4. 跨库对比
   - 可以将指纹数据库复制到其他机器
   - 使用"与外部库对比"功能
   - 找出不同位置的重复视频

相似度设置:
- strict: 严格模式，只找完全相同的
- standard: 标准模式，允许轻微差异
- loose: 宽松模式，可能包含误报
        """
        
        help_window = tk.Toplevel(self.root)
        help_window.title("使用说明")
        help_window.geometry("500x400")
        
        text = scrolledtext.ScrolledText(help_window, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert(tk.END, help_text)
        text.config(state=tk.DISABLED)
    
    def show_about(self):
        """显示关于"""
        messagebox.showinfo("关于", 
            "VideoDedup - 视频快速去重工具\n\n"
            "基于感知哈希技术，智能识别相似视频\n"
            "支持增量扫描和跨库对比\n\n"
            "版本: 1.0.0")
    
    def rename_duplicates(self):
        """重命名重复文件"""
        if not self.duplicate_groups:
            messagebox.showwarning("提示", "请先查找重复视频")
            return
        
        # 创建对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("重命名重复文件")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"将为 {len(self.duplicate_groups)} 组重复视频添加后缀标记",
                 font=('Arial', 10, 'bold')).pack(pady=10)
        
        # 后缀格式
        fmt_frame = ttk.Frame(dialog)
        fmt_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(fmt_frame, text="后缀格式:").pack(side=tk.LEFT)
        suffix_var = tk.StringVar(value="_dup{id:03d}")
        ttk.Entry(fmt_frame, textvariable=suffix_var, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Label(fmt_frame, text="→ 效果: movie_dup001.mp4", foreground='gray').pack(side=tk.LEFT)
        
        # 操作选择
        action_var = tk.StringVar(value="preview")
        ttk.Radiobutton(dialog, text="预览模式（不实际执行）", 
                       variable=action_var, value="preview").pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(dialog, text="立即执行重命名",
                       variable=action_var, value="execute").pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(dialog, text="导出重命名脚本",
                       variable=action_var, value="script").pack(anchor=tk.W, padx=20, pady=2)
        
        def do_rename():
            action = action_var.get()
            suffix = suffix_var.get()
            
            if action == "preview":
                operations = self.dedup.rename_duplicates(
                    self.duplicate_groups, 
                    suffix_format=suffix,
                    dry_run=True
                )
                messagebox.showinfo("预览完成", 
                    f"共 {len(operations)} 个文件将被重命名\n"
                    f"实际执行请选\"立即执行重命名\"")
                
            elif action == "execute":
                if messagebox.askyesno("确认", "确定要重命名这些文件吗？"):
                    operations = self.dedup.rename_duplicates(
                        self.duplicate_groups, 
                        suffix_format=suffix,
                        dry_run=False
                    )
                    success = sum(1 for op in operations if op['status'] == 'success')
                    messagebox.showinfo("完成", 
                        f"重命名完成！\n成功: {success}/{len(operations)}")
                    dialog.destroy()
                    self.find_duplicates()  # 刷新
                    
            elif action == "script":
                filename = filedialog.asksaveasfilename(
                    defaultextension=".sh",
                    filetypes=[("Shell脚本", "*.sh"), ("Batch脚本", "*.bat"), ("所有文件", "*.*")]
                )
                if filename:
                    platform = 'windows' if filename.endswith('.bat') else 'linux'
                    self.dedup.export_rename_script(self.duplicate_groups, filename, platform)
                    messagebox.showinfo("完成", f"脚本已导出:\n{filename}")
                    dialog.destroy()
        
        # 按钮
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="确定", command=do_rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()


def main():
    app = VideoDedupGUI()
    app.run()


if __name__ == '__main__':
    main()
