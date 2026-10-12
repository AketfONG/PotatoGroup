# AGENTS.md — AI Agent 工作规则

本文件面向在本仓库工作的 AI Agent(Cursor / Copilot 等,Cursor 会自动读取)。人类队友请读 `README.md`。

## 项目一句话

前后端分离的即时通讯系统「土豆聊天」:Vue 3 + Naive UI 前端调 RESTful API + WebSocket,FastAPI 后端写 MySQL(SQLite 兼容),消息走「会话链 + 用户链(写扩散)」保证可靠性。

## 关键路径(改哪里找哪里)

| 内容 | 路径 |
|---|---|
| API 契约(Source of Truth) | `docs/02-API约定.md` |
| 后端路由 | `backend/app/api/v1/`(auth / users / friends / conversations / messages / sync / ws) |
| 后端数据模型 | `backend/app/models/`(与 `docs/03-数据库设计.md` 一一对应) |
| 后端请求/响应模型 | `backend/app/schemas/`(Pydantic,与 `docs/02` 一一对应) |
| 业务逻辑 | `backend/app/services/`(消息写扩散、WS 连接管理) |
| 前端 API 层 | `frontend/src/api/`(types.ts = 契约的 TS 版;index.ts = 端点门面;ws.ts = 推送客户端) |
| 前端状态 | `frontend/src/stores/`(user.ts / chat.ts) |
| 部署 | `docs/04-部署方案.md` + `deploy/` + `nginx/` |

## 硬性规则

1. **改 API 必须三件套同步**,且在同一次提交内:`docs/02-API约定.md` + `backend/app/schemas/` + `frontend/src/api/types.ts`。禁止只改一侧,禁止重命名 `docs/02` 中已定字段,只做增量扩展。
2. **本地产物不读不入库**:`.env`、`backend/potato.db`、`.venv/`、`node_modules/`、`dist/`、密钥。`.env.example` 是模板可以改;生产密钥走环境变量 / K8s Secret。
3. **安全实现只用官方成熟库,禁止手搓**:密码哈希用 bcrypt、token 用 PyJWT、CORS 用 FastAPI 中间件(现状见 `backend/app/core/security.py`);前端渲染消息一律按纯文本处理防 XSS。
4. **数据库结构变更必须同步更新 `docs/03-数据库设计.md`**;新增接口必须先在 `docs/02-API约定.md` 立契约再写代码(前端驱动 API 设计)。
5. **风格约定**:代码注释与 UI 文案使用中文;API 字段 `snake_case`;后端统一响应包络 `{code, message, data}` 与错误码表(见 `backend/app/core/errors.py`);前端不直接拼 URL,统一走 `frontend/src/api/index.ts` 门面。
6. **依赖管理**:新增依赖前查 `docs/01-技术选型分析.md`,不引入重型替代库(如换 UI 组件库、换 ORM);前端有 lockfile,禁止用 `npm install` 更新依赖树(用 `npm ci`)。

## 改动后自证(完成任何改动后执行)

```bash
# 前端:类型检查必须通过
cd frontend && npx vue-tsc --noEmit

# 后端:能启动、健康检查通过(启动命令见下)
uvicorn app.main:app --port 8000    # 在 backend/ 且激活 .venv
curl http://127.0.0.1:8000/api/v1/health   # 期望 {"code":0,...}

# 涉及接口改动:打开 http://localhost:8000/docs 核对自动生成的 OpenAPI 与 docs/02 一致
# 涉及前端改动:dev 环境打开 http://localhost:5173 目视确认(中文界面无乱码)
```

## 不要做的事

- 不要绕过 `scripts/setup.sh` / `scripts/dev.sh` 的既有行为,除非用户明确要求;
- 不要在 `main` 直接大改;提交遵循 Conventional Commits(`feat:` / `fix:` / `docs:` + 中文简述);
- 不要为通过类型检查而随手 `any` 或关闭 strict 选项;
- 不要修改 `docs/02` 已定字段名、不要删除 `README.md` 中的交接信息;
- 遇到 `.env` 里出现真实密钥:提醒用户轮换,不要将其复制到代码或文档中。