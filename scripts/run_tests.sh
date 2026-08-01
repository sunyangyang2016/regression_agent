#!/bin/bash
# Agent - 测试运行脚本
# 用法: bash scripts/run_tests.sh [options]

set -e

echo "🧪 Agent 测试运行器"
echo "==================="

# 检测 Python
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "❌ 未安装 Python"
    exit 1
fi

# 检测 pytest
if ! $PYTHON -m pytest --version &>/dev/null; then
    echo "📦 安装测试依赖..."
    $PYTHON -m pip install pytest pytest-cov pytest-asyncio
fi

# 解析参数
COVERAGE=false
VERBOSE=false
TEST_PATH="tests/"
MARKER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --coverage) COVERAGE=true; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --unit) TEST_PATH="tests/unit/"; shift ;;
        --integration) TEST_PATH="tests/integration/"; shift ;;
        --file) TEST_PATH="$2"; shift 2 ;;
        --marker) MARKER="-m $2"; shift 2 ;;
        --help) echo "用法: bash scripts/run_tests.sh [--coverage] [--verbose] [--unit|--integration|--file <path>] [--marker <marker>]"; exit 0 ;;
        *) TEST_PATH="$1"; shift ;;
    esac
done

# 构建参数
ARGS=""
if $COVERAGE; then
    ARGS="$ARGS --cov=. --cov-report=term --cov-report=html"
    echo "📊 覆盖率报告已启用"
fi
if $VERBOSE; then
    ARGS="$ARGS -v"
fi

# 生成前端模板（确保测试前模板是最新的）
echo "🎨 检查前端模板..."
$PYTHON ui/gen_template.py 2>/dev/null || true

# 运行测试
echo ""
echo "📋 测试路径: $TEST_PATH"
echo "🚀 开始测试..."
echo ""

$PYTHON -m pytest $TEST_PATH $ARGS $MARKER

# 检查结果
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ 所有测试通过！"
else
    echo ""
    echo "❌ 测试失败 (exit code: $EXIT_CODE)"
fi

# 覆盖率报告路径
if $COVERAGE; then
    echo "📊 HTML 覆盖率报告: htmlcov/index.html"
fi

exit $EXIT_CODE