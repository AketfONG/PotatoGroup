#!/bin/sh
# 后端启动脚本(课程手册要求容器用 start.sh 启动)。
# 监听 0.0.0.0:80 —— SECoder 的 Service 以容器命名端口 http(80) 为 targetPort。
set -eu

# 单副本 + 进程内 WS 连接表(connection_manager),因此不使用多 worker。
exec uvicorn app.main:app --host 0.0.0.0 --port 80
