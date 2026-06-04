#!/bin/bash
# ============================
# AI-DocAgent 单文件处理脚本
# 用法: bash shell/run_single.sh <文件路径>
# ============================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

FILE_PATH="$1"
OUTPUT="${2:-output/$(basename "$FILE_PATH" | sed 's/\.[^.]*$//')_$(date +%Y%m%d_%H%M%S).json}"

if [ -z "$FILE_PATH" ]; then
    echo "用法: $0 <文档路径> [输出路径]"
    echo "示例: $0 docs/sample.pdf output/result.json"
    exit 1
fi

if [ ! -f "$FILE_PATH" ]; then
    echo "[ERROR] 文件不存在: $FILE_PATH"
    exit 1
fi

# 激活环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
fi

# 创建输出目录
mkdir -p "$(dirname "$OUTPUT")"

echo "=========================================="
echo " AI-DocAgent 单文件处理"
echo "=========================================="
echo " 输入文件: $FILE_PATH"
echo " 输出文件: $OUTPUT"
echo " 开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 步骤1: 解析文档
echo ""
echo "[Step 1/3] 文档解析..."
PARSE_OUTPUT="output/.tmp_parse_$(date +%s).json"
docagent parse "$FILE_PATH" -o "$PARSE_OUTPUT" -f json

# 步骤2: LLM抽取
echo ""
echo "[Step 2/3] LLM信息抽取..."
docagent extract --file "$FILE_PATH" -o "$OUTPUT"

# 步骤3: 校验
echo ""
echo "[Step 3/3] 数据校验..."
docagent validate --file "$OUTPUT" -o "output/errors_$(date +%Y%m%d_%H%M%S).json"

# 清理临时文件
rm -f "$PARSE_OUTPUT"

echo ""
echo "=========================================="
echo " 处理完成！"
echo " 结果: $OUTPUT"
echo " 完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
