#!/bin/bash
# Agent - 构建脚本
# 用法: bash scripts/build.sh [options]

set -e

echo "🔨 Agent 构建工具"
echo "=================="

# 解析参数
CLEAN=false
BUILD_DOCKER=false
BUILD_PYTHON=false
GEN_TEMPLATE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean) CLEAN=true; shift ;;
        --docker) BUILD_DOCKER=true; shift ;;
        --python) BUILD_PYTHON=true; shift ;;
        --template) GEN_TEMPLATE=true; shift ;;
        --all) BUILD_DOCKER=true; BUILD_PYTHON=true; GEN_TEMPLATE=true; shift ;;
        --help) echo "用法: bash scripts/build.sh [--clean] [--docker] [--python] [--template] [--all]"; exit 0 ;;
        *) echo "❌ 未知参数: $1"; exit 1 ;;
    esac
done

# 默认行为：如果没有任何参数，执行全部
if ! $CLEAN && ! $BUILD_DOCKER && ! $BUILD_PYTHON && ! $GEN_TEMPLATE; then
    BUILD_PYTHON=true
    GEN_TEMPLATE=true
fi

# 清理
if $CLEAN; then
    echo "🧹 清理构建产物..."
    rm -rf dist/ build/ *.egg-info/
    rm -rf ui/template/main_layout.html
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    echo "✅ 清理完成"
fi

# 检测 Python
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "❌ 未安装 Python"
    exit 1
fi

# 生成前端模板
if $GEN_TEMPLATE; then
    echo "🎨 生成前端模板..."
    $PYTHON ui/gen_template.py
    echo "✅ 模板生成完成"
fi

# 构建 Python 包
if $BUILD_PYTHON; then
    echo "📦 构建 Python 包..."
    if ! $PYTHON -m pip install build --quiet; then
        $PYTHON -m pip install build
    fi
    $PYTHON -m build
    echo "✅ Python 包构建完成"
    echo "📁 输出: dist/"
fi

# 构建 Docker 镜像
if $BUILD_DOCKER; then
    echo "🐳 构建 Docker 镜像..."
    docker build -t agent:latest .
    echo "✅ Docker 镜像构建完成"
    echo "💡 运行: docker-compose up -d"
fi

echo ""
echo "✅ 构建完成！"