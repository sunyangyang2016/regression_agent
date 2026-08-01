#!/bin/bash
# Agent - 开发环境设置脚本
# 用法: bash scripts/setup_dev.sh

set -e

echo "🚀 Agent 开发环境设置..."

# 检测操作系统
OS="$(uname -s)"
case "$OS" in
    Linux*)   PLATFORM=linux;;
    Darwin*)  PLATFORM=mac;;
    MINGW*|MSYS*|CYGWIN*)  PLATFORM=windows;;
    *)        echo "❌ 未知操作系统: $OS"; exit 1;;
esac

echo "📋 检测到平台: $PLATFORM"

# 检查 Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "❌ 未安装 Python，请先安装 Python 3.10+"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo "✅ Python: $($PYTHON --version)"

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "📦 创建虚拟环境..."
    $PYTHON -m venv .venv
    echo "✅ 虚拟环境已创建"
else
    echo "✅ 虚拟环境已存在"
fi

# 激活虚拟环境并安装依赖
case "$PLATFORM" in
    windows)
        VENV_PYTHON=".venv/Scripts/python"
        VENV_PIP=".venv/Scripts/pip"
        echo "💡 请运行: .venv\\Scripts\\activate"
        ;;
    *)
        VENV_PYTHON=".venv/bin/python"
        VENV_PIP=".venv/bin/pip"
        source .venv/bin/activate
        ;;
esac

# 升级 pip
$VENV_PYTHON -m pip install --upgrade pip

# 安装项目依赖
echo "📦 安装项目依赖..."
$VENV_PIP install -e ".[dev]"

# 配置 pre-commit
if command -v pre-commit &>/dev/null || $VENV_PIP install pre-commit; then
    echo "🔧 配置 pre-commit..."
    $VENV_PYTHON -m pre_commit install 2>/dev/null || true
fi

# 创建 .env（如果不存在）
if [ ! -f ".env" ]; then
    echo "📝 创建 .env 配置文件..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件填入您的 API Key"
fi

# 创建必要目录
echo "📁 创建必要目录..."
mkdir -p logs data tests/.coverage

# 生成前端模板
echo "🎨 生成前端模板..."
$VENV_PYTHON ui/gen_template.py

echo ""
echo "✅ Agent 开发环境设置完成！"
echo ""
echo "💡 启动应用:"
echo "   $VENV_PYTHON main.py"
echo ""
echo "💡 运行测试:"
echo "   $VENV_PYTHON -m pytest"