#!/usr/bin/env bash
# ============================================================
# 一键同时启动前后端开发服务器(无 Docker)
#
# 使用:bash scripts/dev.sh
# 前端:http://localhost:5173   后端 API:http://localhost:8000/docs
# Ctrl+C 退出时,两个服务进程一并结束。
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
info() { echo -e "${GREEN}[dev]${NC} $*"; }
fail() { echo -e "${RED}[dev] 失败:${NC} $*" >&2; exit 1; }

# 前置检查:确保已经跑过 setup.sh
[[ -x "$BACKEND_DIR/.venv/bin/uvicorn" ]] || fail "后端环境未就绪,请先运行:bash scripts/setup.sh"
[[ -d "$FRONTEND_DIR/node_modules" ]]     || fail "前端依赖未安装,请先运行:bash scripts/setup.sh"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  info "正在停止所有服务..."
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null || true
  # 等待子进程退出,避免残留孤儿进程
  wait 2>/dev/null || true
  info "已全部停止"
}
trap cleanup EXIT INT TERM

# ---------- 启动后端 ----------
info "启动后端(uvicorn, http://127.0.0.1:8000)..."
(cd "$BACKEND_DIR" && .venv/bin/uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

# ---------- 启动前端 ----------
info "启动前端(vite, http://localhost:5173)..."
(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

info "两个服务已启动,按 Ctrl+C 退出"
info "前端页面 http://localhost:5173 | API 文档 http://localhost:8000/docs"

# 任一进程退出则整体结束
wait -n "$BACKEND_PID" "$FRONTEND_PID"
info "检测到服务退出,正在清理..."