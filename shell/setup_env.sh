#!/bin/bash
# ============================
# AI-DocAgent 环境初始化脚本
# 用法: source shell/setup_env.sh
# ============================
set -e

echo "=========================================="
echo " AI-DocAgent - 环境初始化"
echo "=========================================="

# 检测Python版本
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
            PYTHON_CMD=$cmd
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] 未找到Python 3.8+，请先安装Python"
    return 1
fi

echo "[INFO] 使用Python: $PYTHON_CMD ($version)"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "[INFO] 创建虚拟环境..."
    $PYTHON_CMD -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null
echo "[INFO] 虚拟环境已激活"

# 安装依赖
echo "[INFO] 安装项目依赖..."
pip install -e . --quiet 2>&1 | tail -5

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "[WARN] .env 文件不存在，从 .env.example 复制..."
    cp .env.example .env
    echo "[INFO] 已创建 .env 文件，请编辑填入实际的API密钥和数据库配置"
fi

# 创建必要的目录
mkdir -p logs status data conf

echo ""
echo "=========================================="
echo " 环境初始化完成！"
echo " 下一步: 编辑 .env 文件填入API密钥"
echo " 运行: docagent --help 查看使用帮助"
echo "=========================================="
