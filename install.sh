#!/usr/bin/env bash
# BuaaGetPPt 一键安装脚本：创建虚拟环境并安装全部依赖
set -e
cd "$(dirname "$0")"

# 选择可用的 Python
if command -v python >/dev/null 2>&1; then
  PY=python
elif command -v py >/dev/null 2>&1; then
  PY=py
else
  echo "❌ 未找到 python，请先安装 Python 3.10+ 并加入 PATH" >&2
  exit 1
fi

echo "Python：$($PY --version 2>&1)"

# 创建虚拟环境（已存在则跳过）
if [ ! -d .venv ]; then
  echo "📦 [1/2] 创建虚拟环境……"
  "$PY" -m venv .venv
else
  echo "📦 [1/2] 虚拟环境已存在，跳过创建"
fi

# 兼容 Windows 与 macOS/Linux 的目录布局
if [ -x ".venv/Scripts/python.exe" ]; then
  VPY=".venv/Scripts/python.exe"
else
  VPY=".venv/bin/python"
fi

echo "📥 [2/2] 安装依赖……"
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -r requirements.txt

echo ""
echo "✅ 安装完成！接下来："
echo "   网页界面：$VPY webui.py    （自动打开 http://127.0.0.1:8765）"
echo "   命令行  ：$VPY main.py \"回放页链接\""
