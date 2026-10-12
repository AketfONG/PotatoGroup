#!/usr/bin/env bash
# ============================================================
# 土豆聊天(Potato Messenger)本地环境一键初始化(无 Docker)
#
# 用途:clone 之后执行一次,即可获得与开发环境一致的可运行环境;
#      脚本幂等,可反复执行,不会破坏已有配置(如 .env)。
#
# 使用:bash scripts/setup.sh
# ============================================================
set -euo pipefail

# ---------- 通用 ----------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[setup]${NC} $*"; }
fail()  { echo -e "${RED}[setup] 失败:${NC} $*" >&2; exit 1; }

# ---------- 1. 前置检查 ----------
info "检查依赖工具版本..."

command -v python3 >/dev/null 2>&1 \
  || fail "未找到 python3,请先安装 Python 3.11+ (https://www.python.org/downloads/)"

command -v node >/dev/null 2>&1 \
  || fail "未找到 node,请先安装 Node.js 18+ (建议 https://nodejs.org/ LTS 版本)"

PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$(uname -s)" == "Darwin" && "$PY_VERSION" == "3.9" ]]; then
  # macOS 自带的 /usr/bin/python3 恰好也是 3.9,这里只提示
  warn "检测到 python3 为 $PY_VERSION,项目要求 3.11+"
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "python3 版本过低(当前 $PY_VERSION),本项目需要 3.11+"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
(( NODE_MAJOR >= 18 )) \
  || fail "node 版本过低(当前 $(node --version)),需要 18+"

command -v npm >/dev/null 2>&1 || fail "未找到 npm,请随 Node.js 一并安装"

info "工具检查通过:python3 $PY_VERSION / node v$(node --version | tr -d 'v')"

# ---------- 2. 后端环境 ----------
info "配置后端(backend/)..."

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  info "创建虚拟环境 backend/.venv ..."
  (cd "$BACKEND_DIR" && python3 -m venv .venv)
else
  info "虚拟环境已存在,跳过创建"
fi

info "安装后端 Python 依赖(requirements.txt)..."
"$BACKEND_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$BACKEND_DIR/.venv/bin/pip" install --quiet -r "$BACKEND_DIR/requirements.txt"
info "后端依赖安装完成"

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  info "生成 backend/.env(基于 .env.example,请按需修改)"
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  warn "默认使用 SQLite;切换 MySQL 请编辑 backend/.env 中的 DATABASE_URL"
else
  info "backend/.env 已存在,保持不动"
fi

# SQLite 数据库无需手动创建:首次 uvicorn 启动时自动建表

# ---------- 3. 前端环境 ----------
info "配置前端(frontend/)..."

cd "$FRONTEND_DIR"
if [[ -f package-lock.json ]]; then
  info "检测到 package-lock.json,使用 npm ci 保证依赖树与提交版本一致"
  npm ci --silent
else
  warn "未找到 package-lock.json,回退到 npm install(建议提交 lockfile)"
  npm install --silent
fi
info "前端依赖安装完成"

# ---------- 4. 完成 ----------
echo
info "初始化完成!下一步:"
echo "  ─────────────────────────────────────────────"
echo "  1) 一键同时启动前后端:  bash scripts/dev.sh"
echo "     (或分开启动:"
echo "       后端  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000"
echo "       前端  cd frontend && npm run dev)"
echo "  2) 打开前端页面:       http://localhost:5173"
echo "  3) 后端 API 文档:      http://localhost:8000/docs"
echo "  ─────────────────────────────────────────────"
echo "  本地默认使用 SQLite,数据文件 backend/potato.db(已被 gitignore)"
echo "  首次使用请先在前端注册账号"