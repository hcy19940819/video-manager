#!/bin/bash
# VideoDedup 使用示例脚本

echo "=== VideoDedup 使用示例 ==="
echo ""

# 示例1: 扫描单个目录
echo "1. 扫描视频目录生成指纹..."
echo "   python videodedup.py scan ~/Videos"
echo ""

# 示例2: 扫描多个目录
echo "2. 扫描多个目录..."
echo "   python videodedup.py scan ~/Videos ~/Downloads ~/Backup"
echo ""

# 示例3: 完整重新扫描
echo "3. 完整重新扫描（忽略已有指纹）..."
echo "   python videodedup.py scan ~/Videos --full"
echo ""

# 示例4: 查找所有重复
echo "4. 查找重复视频..."
echo "   python videodedup.py find"
echo ""
echo "   # 查找后会自动生成："
echo "   # - duplicates.md    Markdown报告"
echo "   # - duplicates.json  JSON数据"
echo "   # - report.html      📊 HTML可视化报告（推荐在浏览器打开）"
echo ""

# 示例5: 打开HTML可视化报告
echo "5. 打开HTML可视化报告..."
echo "   # macOS"
echo "   open report.html"
echo "   # Linux"
echo "   xdg-open report.html"
echo "   # Windows"
echo "   start report.html"
echo ""

# 示例6: 跨目录对比
echo "6. 跨目录对比（只找不同目录间的重复）..."
echo "   python videodedup.py find --cross"
echo ""

# 示例7: 重命名标记重复文件（预览模式）
echo "7. 重命名标记重复文件 - 预览..."
echo "   python videodedup.py rename --groups duplicates.json"
echo ""

# 示例8: 重命名标记重复文件（实际执行）
echo "8. 重命名标记重复文件 - 执行..."
echo "   python videodedup.py rename --groups duplicates.json --execute"
echo ""

# 示例9: 自定义后缀格式
echo "9. 自定义后缀格式（中文）..."
echo "   python videodedup.py rename --groups duplicates.json --suffix '_重复{id}' --execute"
echo ""

# 示例10: 导出重命名脚本
echo "10. 导出重命名脚本..."
echo "   python videodedup.py rename --groups duplicates.json -o rename.sh"
echo "   # 或 Windows: -o rename.bat"
echo ""

# 示例11: 对比外部库
echo "11. 与外部指纹库对比..."
echo "   python videodedup.py compare /mnt/external/videodedup.db"
echo ""

# 示例12: 使用自定义数据库路径
echo "12. 使用自定义数据库..."
echo "   python videodedup.py --db ~/movies.db scan ~/Movies"
echo "   python videodedup.py --db ~/movies.db find"
echo ""

# 示例13: 多线程加速
echo "13. 使用8线程加速扫描..."
echo "   python videodedup.py --workers 8 scan ~/Videos"
echo ""

echo "=== 推荐工作流程（使用HTML报告）==="
echo ""
echo "# 步骤1: 扫描主视频库"
echo "python videodedup.py --db main.db scan ~/Videos"
echo ""
echo "# 步骤2: 查找重复"
echo "python videodedup.py --db main.db find"
echo ""
echo "# 步骤3: 在浏览器中打开 report.html 可视化报告"
echo "open report.html"
echo ""
echo "# 步骤4: 在HTML报告中："
echo "# - 查看缩略图对比"
echo "# - 勾选要删除的文件"
echo "# - 点击'生成删除脚本'按钮"
echo ""
echo "# 步骤5: 审核并执行删除脚本"
echo "cat delete_duplicates.sh"
echo "bash delete_duplicates.sh"
echo ""
echo "=== 或者使用重命名方式 ==="
echo ""
echo "# 步骤4b: 预览重命名效果"
echo "python videodedup.py rename --groups duplicates.json"
echo ""
echo "# 步骤5b: 执行重命名（添加 _dupXXX 后缀）"
echo "python videodedup.py rename --groups duplicates.json --execute"
echo ""
echo "# 步骤6b: 手动处理带 _dupXXX 后缀的文件"
echo "# - 按文件名排序，所有重复文件会聚在一起"
echo "# - 对比文件大小、分辨率等，决定保留哪个"
echo "# - 删除不需要的重复文件"
echo ""
