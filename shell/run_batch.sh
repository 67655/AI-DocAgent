#!/bin/bash
# ============================
# AI-DocAgent 批量任务调度脚本
# 用法: bash shell/run_batch.sh [选项]
# ============================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 默认参数
INPUT_DIR="${INPUT_DIR:-}"
INPUT_FILE="${INPUT_FILE:-}"
OUTPUT="${OUTPUT:-output/batch_result_$(date +%Y%m%d_%H%M%S).jsonl}"
SHARD_SIZE="${SHARD_SIZE:-10}"
PROVIDER="${PROVIDER:-qwen}"
CONTINUE="${CONTINUE:-false}"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            INPUT_DIR="$2"; shift 2 ;;
        --file)
            INPUT_FILE="$2"; shift 2 ;;
        --output|-o)
            OUTPUT="$2"; shift 2 ;;
        --shard-size)
            SHARD_SIZE="$2"; shift 2 ;;
        --provider)
            PROVIDER="$2"; shift 2 ;;
        --continue)
            CONTINUE="true"; shift ;;
        *)
            echo "未知参数: $1"
            echo "用法: $0 [--dir <文档目录>] [--file <文件列表>] [-o <输出>] [--shard-size <N>] [--provider <厂商>] [--continue]"
            exit 1 ;;
    esac
done

# 参数校验
if [ -z "$INPUT_DIR" ] && [ -z "$INPUT_FILE" ]; then
    echo "[ERROR] 请提供 --dir 或 --file 参数"
    echo "用法: $0 --dir ./docs/ -o result.jsonl"
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

# 构建命令
CMD="docagent batch --shard-size $SHARD_SIZE --provider $PROVIDER -o $OUTPUT"

if [ -n "$INPUT_DIR" ]; then
    CMD="$CMD --dir $INPUT_DIR"
elif [ -n "$INPUT_FILE" ]; then
    CMD="$CMD --file $INPUT_FILE"
fi

echo "=========================================="
echo " AI-DocAgent 批量任务调度"
echo "=========================================="
echo " 输入: ${INPUT_DIR:-$INPUT_FILE}"
echo " 输出: $OUTPUT"
echo " 分片大小: $SHARD_SIZE"
echo " LLM: $PROVIDER"
echo " 开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 执行
$CMD

EXIT_CODE=$?
echo ""
echo "=========================================="
echo " 完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo " 退出码: $EXIT_CODE"
echo "=========================================="

exit $EXIT_CODE
