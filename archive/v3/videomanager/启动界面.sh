#!/bin/bash
# 视频管家 - 启动脚本

cd "$(dirname "$0")"

echo "========================================"
echo "🎬 视频管家 - 库管理可视化界面"
echo "========================================"
echo ""

# 检查依赖
if ! python3 -c "import flask" 2>/dev/null; then
    echo "正在安装 Flask..."
    pip3 install flask -q
fi

echo "启动 Web 界面..."
echo ""
echo "📱 访问地址: http://localhost:5000"
echo "🌐 局域网访问: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "按 Ctrl+C 停止服务"
echo "========================================"
echo ""

python3 库管理界面.py
