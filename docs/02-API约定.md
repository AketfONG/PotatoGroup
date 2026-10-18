# 02 API 契约(RESTful)

> 本文档是前后端共同遵守的 **Source of Truth**。后端 Pydantic 模型(`backend/app/schemas/`)与前端 TypeScript 类型(`frontend/src/api/types.ts`)必须与本文档保持一致。
> 设计原则:**前端驱动 API 设计** —— 接口以满足前端页面需求为目标,而不是让前端绕着接口凑数据;字段命名遵循 REST 资源语义。

## 1. 通用约定

### 1.1 基础信息

| 项 | 约定 |
|---|---|
| Base URL | `/api/v1` |
| 数据格式 | `application/json; charset=utf-8`(UTF-8) |
| 时间格式 | Unix 时间戳(秒,`int`),字段名后缀 `_time` |
| ID | 整数自增 |
| 命名 | 字段使用 `snake_case` |
| HTTP 语义 | GET 安全/幂等,PUT/PATCH/DELETE 幂等,POST 非幂等 |

### 1.2 统一响应包络

所有 REST 接口返回统一包络(WebSocket 事件除外):

```json
{ "code": 0, "message": "ok", "data": { } }
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | int | `0` 表示成功;非 0 见错误码表 |
| `message` | string | 人类可读信息(中文),`code != 0` 时为错误描述 |
| `data` | object/null | 业务数据,出错时为 `null` |

### 1.3 错误码约定

HTTP 状态码与业务错误码双层设计:HTTP 表达传输/鉴权层错误,`code` 表达业务错误。

| HTTP | code | 含义 |
|---|---|---|
| 200/201 | 0 | 成功 |
| 400 | 1001 | 参数格式错误(校验失败) |
| 401 | 1002 | 未登录 / token 失效 |
| 403 | 1003 | 无权限(非本人资源、非群管理员等) |
| 404 | 1004 | 资源不存在 |
| 409 | 2001 | 用户名已存在 |
| 409 | 2002 | 重复的好友申请 / 已是好友 |
| 409 | 2003 | 会话名已存在 / 已在群中 |
| 422 | 1001 | 请求体无法解析/校验失败(FastAPI 默认 422,统一并入 1001) |
| 500 | 9001 | 服务器内部错误 |

### 1.4 鉴权

- 登录成功后签发 JWT: `{ "sub": "<user_id>", "exp": <ts> }`,有效期 7 天;
- REST:`Authorization: Bearer <token>`;
- WebSocket:`/ws?token=<token>`(握手 401 即断开);
- 密码使用 bcrypt 加盐哈希存储,**任何接口不得返回 `password` 字段**。

### 1.5 游标分页(cursor)

消息类列表不使用页码,而使用**时间游标**:

| 参数 | 说明 |
|---|---|
| `cursor` | 上次获取到的最后一条消息的 `msg_id`/时间戳;缺省表示从最新开始往前取 |
| `limit` | 本次最多返回条数,默认 50 |
| 返回 `data.next_cursor` | 为 `null` 表示没有更多历史;继续翻页时作为 `cursor` 传入 |

## 2. 认证 `/auth`

| 方法 | 路径 | 说明 | 请求体 | 响应 `data` |
|---|---|---|---|---|
| POST | `/api/v1/auth/register` | 注册 | `{ "name": "土豆", "password": "•••" }` | `{ "user_id": 1 }` |
| POST | `/api/v1/auth/login` | 登录 | `{ "name": "土豆", "password": "•••" }` | `{ "token": "eyJ...", "user": { …User 摘要 } }` |
| DELETE | `/api/v1/auth/logout` | 登出(需鉴权) | — | `null`(客户端丢弃 token;JWT 无状态,黑名单在扩展章节处理) |

校验规则:`name` 2–32 个字符(允许中文);`password` 8–64 位,至少含字母与数字。

## 3. 用户 `/users`

| 方法 | 路径 | 说明 | 响应 `data` |
|---|---|---|---|
| GET | `/api/v1/users/me` | 我的资料(需鉴权) | `UserProfile` |
| PATCH | `/api/v1/users/me` | 修改资料(需鉴权) | `UserProfile` |
| GET | `/api/v1/users?keyword=土豆` | 按用户名前缀搜索(加好友用,需鉴权) | `{ "items": [UserSummary] }` |
| GET | `/api/v1/users/{user_id}` | 查看公开资料(需鉴权) | `UserSummary` |
| DELETE | `/api/v1/users/me` | 注销账号(需当前密码确认,级联清理社交/会话数据,需鉴权) | `null` |

**UserSummary**:`{ user_id, name, avatar, online }`
**UserProfile**:`{ user_id, name, avatar, email, phone, register_time, login_time }`
**UserUpdateIn**:`{ name?, avatar?, email?, phone?, old_password?, new_password? }`
修改密码:`PATCH /users/me` 请求体携带 `{ "old_password": "...", "new_password": "..." }`,需通过旧密码校验;新密码与注册规则一致(8–64 位,至少含字母与数字)。

注销:`DELETE /users/me` 请求体为 `{ "password": "•••" }`,用于二次确认。服务端清理好友关系、好友申请、会话成员关系与用户链;私聊会话及其消息整体删除;群聊保留历史消息但将发送者置空;群主注销时优先转让给管理员,其次最早加入的成员,无剩余成员则删除群聊。

## 4. 好友 `/friends` 与 `/friend-requests`

| 方法 | 路径 | 说明 | 响应 `data` |
|---|---|---|---|
| GET | `/api/v1/friends` | 好友列表(含备注、分组) | `{ "items": [FriendItem] }` |
| DELETE | `/api/v1/friends/{friend_user_id}` | 删除好友 | `null` |
| POST | `/api/v1/friend-requests` | 发起好友申请 `{ "target_user_id": 5 }` | `{ "request_id": 1 }` |
| GET | `/api/v1/friend-requests` | 我收到/发出的申请列表 | `{ "items": [FriendRequest] }` |
| POST | `/api/v1/friend-requests/{request_id}/accept` | 同意 | `null` |
| POST | `/api/v1/friend-requests/{request_id}/reject` | 拒绝 | `null` |

**FriendItem**:`{ user_id, name, avatar, remark, group_name, online }`
**FriendRequest**:`{ request_id, from_user: UserSummary, to_user_id, status: "pending"|"accepted"|"rejected", create_time }`

好友关系为双向存储(两行记录),保证双方各自拉取列表均为单表查询。

## 5. 会话 `/conversations`

单聊与群聊统一为 **conversation**;单聊 `type="private"`,群聊 `type="group"`。

| 方法 | 路径 | 说明 | 响应 `data` |
|---|---|---|---|
| GET | `/api/v1/conversations` | 我的会话列表(含未读数、置顶、免打扰) | `{ "items": [ConversationItem] }` |
| POST | `/api/v1/conversations` | 创建群聊 `{ "name": "土豆群", "member_ids": [2,3] }` | `Conversation` |
| POST | `/api/v1/conversations/private` | 创建/获取与某用户的单聊 `{ "target_user_id": 2 }` | `Conversation` |
| GET | `/api/v1/conversations/{id}` | 会话详情(群名、成员、公告) | `Conversation` |
| PATCH | `/api/v1/conversations/{id}` | 改群名/公告(群主或管理员) | `Conversation` |
| POST | `/api/v1/conversations/{id}/members` | 邀请好友入群 `{ "user_ids": [4] }`(需群主/管理员审批通过才生效,骨架阶段直接加入) | `{ "items": [Member] }` |
| DELETE | `/api/v1/conversations/{id}/members/{user_id}` | 移出群(群主可移除任何人;管理员可移除普通成员) | `null` |
| POST | `/api/v1/conversations/{id}/members/me` | 主动退群 | `null` |
| PATCH | `/api/v1/conversations/{id}/me` | 置顶 / 免打扰 `{ "pinned": true, "muted": false }` | `null` |

**ConversationItem**:`{ conversation_id, name, type, avatar, member_count, last_msg: MessageSummary|null, unread_count, pinned, muted, update_time }`
**Member**:`{ user: UserSummary, role: "owner"|"admin"|"member", join_time }`
**Conversation**:`{ conversation_id, name, type, avatar, owner_id, announcement, members: [Member], create_time, update_time }`

## 6. 消息 `/conversations/{id}/messages` 与同步 `/sync`

| 方法 | 路径 | 说明 | 响应 `data` |
|---|---|---|---|
| POST | `/api/v1/conversations/{id}/messages` | 发送文本消息 `{ "body": "你好", "reply_to": null }`(可以是已读回执/撤回前的消息) | `Message` |
| GET | `/api/v1/conversations/{id}/messages?cursor=&limit=&sender_id=&start_time=&end_time=` | 会话历史(按时间游标翻页,可按发送者/时间段过滤;**新成员可拉取入群前历史**) | `{ "items": [Message], "next_cursor": int|null }` |
| POST | `/api/v1/conversations/{id}/messages/{msg_id}/recall` | 撤回(仅发送者本人,2 分钟内;实现为向用户链投递命令消息) | `null` |
| DELETE | `/api/v1/conversations/{id}/messages/{msg_id}` | 本地删除(仅自己的用户链中移除) | `null` |
| POST | `/api/v1/conversations/{id}/read` | 上报已读 `{ "read_index": 42 }`(更新 conversation_member.read_index) | `null` |
| GET | `/api/v1/sync?cursor=&limit=` | **兜底拉取**:拉取我的用户链上 cursor 之后的消息(离线补拉/断线补拉) | `{ "items": [Message], "next_cursor": int|null }` |

**Message**:`{ msg_id, conversation_id, sender_id, body, reply_to, create_time, seq }`
其中 `seq` 为该消息在**我的用户链**中的序号(全局递增),`cursor` 一致性校验以 `seq` 为准。

### 消息分发模型(与需求文档一致)

1. **消息发送**:客户端 POST 上行;
2. **消息分发**:服务端写入「会话链」(conversation 维度,供历史拉取)并为每个成员写入「用户链」(inbox 维度,含 seq);
3. **消息送达**:对在线成员走 WebSocket 推送;离线成员登录后通过 `/sync` 补拉;
4. **消息处理**:客户端按事件类型渲染/刷新未读数。

## 7. WebSocket 协议 `/ws`

- 连接:`ws(s)://<host>/ws?token=<JWT>`;心跳:客户端每 30s 发送 `{"type":"ping"}`,服务端回复 `{"type":"pong"}`;
- 服务端推送事件格式:

```json
{ "type": "message.new", "seq": 102, "prev_seq": 101, "data": { "msg_id": 9, "conversation_id": 1, "sender_id": 2, "body": "你好", "reply_to": null, "create_time": 1760000000 } }
```

| 事件 type | 触发 | `data` |
|---|---|---|
| `message.new` | 新消息(含单聊/群聊) | `Message`;`prev_seq` 为该接收事件用户自己用户链上上一条消息的 seq,客户端比对本地 cursor,不一致立即调用 `/sync` 补拉 |
| `message.recall` | 有人撤回消息 | `{ msg_id, conversation_id }` |
| `message.delete` | 本端多设备同步删除 | `{ msg_id, conversation_id }` |
| `read.sync` | 其他端上报已读(多端同步) | `{ conversation_id, read_index }` |
| `friend.request` | 收到好友申请 | `FriendRequest` |
| `conversation.update` | 群信息/成员变动 | `Conversation` |

- 客户端上行仅允许 `ping`;业务操作一律走 REST,保证 API 可审计、幂等语义清晰。

## 8. 安全约定(课程讲义硬性要求)

1. **前端不可信原则**:后端对一切输入做 Pydantic 校验 + 权限判断,不依赖前端校验;
2. **CORS**:仅放行配置中的前端来源(`CORS_ORIGINS`),`allow_credentials` 按需开启;
3. **密码**:bcrypt 加盐哈希;登录失败统一返回"用户名或密码错误"防枚举;
4. **传输**:生产环境强制 HTTPS(SECoder Ingress TLS),禁止明文 HTTP;
5. **注入**:全程使用 ORM 参数化查询,禁止拼接 SQL;
6. **XSS**:前端渲染消息一律按纯文本/受控转义处理(后续富文本阶段引入白名单过滤);
7. **鉴权**:所有 `/users|/friends|/conversations|/sync` 接口要求 JWT;好友关系、群成员资格在服务端逐一校验。