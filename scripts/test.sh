#!/bin/sh
# 后端单测 + 报告生成(GitLab CI 的 unit-test 作业调用)。
#
# 产出:
#   coverage-reports/coverage.xml      Coverage.py 的 Cobertura 报告 -> Sonar 覆盖率
#   xunit-reports/xunit-result.xml     JUnit 报告 -> Sonar 测试用例数
#
# 必须从**仓库根目录**运行:覆盖率报告里的路径依赖于此
# (见 .coveragerc 的 source = .,否则 Sonar 无法把报告对应到源码)。
#
# 注意:不要用 `-m pytest --cov` 直接跑,那样会绕过 .coveragerc 的 source 设置。
# 这里刻意分两步:coverage run 采集 -> coverage xml 转换,
# 并在末尾保留 pytest 的退出码,使测试失败时流水线立即停止。
set -u

mkdir -p coverage-reports xunit-reports

PYTHON="${PYTHON:-python3}"
if [ -x "backend/.venv/bin/python" ]; then
    PYTHON="backend/.venv/bin/python"
fi

echo "[test] 使用解释器: $PYTHON"

"$PYTHON" -m coverage run \
    -m pytest backend/tests \
    --junit-xml=xunit-reports/xunit-result.xml
ret=$?

# 无论测试是否失败都产出报告,便于在 CI 中直接查看失败原因
"$PYTHON" -m coverage xml -o coverage-reports/coverage.xml
"$PYTHON" -m coverage report

if [ "$ret" -ne 0 ]; then
    echo "[test] 测试失败,退出码 $ret"
    exit "$ret"
fi

# 覆盖率门槛:课程要求后端单测覆盖率 >= 80%
"$PYTHON" -m coverage report --fail-under=80
exit $?
