#!/bin/sh
# 后端单测 + 报告生成(GitLab CI 的 unit-test 作业调用)。
#
# 产出:
#   coverage-reports/coverage.xml      Cobertura 报告 -> Sonar 覆盖率
#   xunit-reports/xunit-result.xml     JUnit 报告    -> Sonar 测试用例数
#
# 必须从**仓库根目录**运行:覆盖率报告里的路径依赖于此
# (见 .coveragerc 的 source = .,否则 Sonar 无法把报告对应到源码)。
#
# 为什么直接调 pytest 而不用 `coverage run -m pytest`:
# pytest.ini 的 addopts 已含 --cov(pytest-cov),覆盖率范围与阈值由它统一负责。
# 若在它外面再套一层 `coverage run`,会形成双重插桩,覆盖率数据不可信。
set -u

mkdir -p coverage-reports xunit-reports

PYTHON="${PYTHON:-python3}"
if [ -x "backend/.venv/bin/python" ]; then
    PYTHON="backend/.venv/bin/python"
fi

echo "[test] 使用解释器: $PYTHON"

# 覆盖率范围/阈值/报告路径全部来自 pytest.ini,这里只追加 JUnit 报告。
"$PYTHON" -m pytest backend/tests \
    --junit-xml=xunit-reports/xunit-result.xml
ret=$?

if [ "$ret" -ne 0 ]; then
    echo "[test] 测试或覆盖率门槛未通过,退出码 $ret"
    echo "[test] 报告仍已产出,便于排查:"
    ls -l coverage-reports xunit-reports 2>/dev/null || true
    exit "$ret"
fi

echo "[test] 通过"
ls -l coverage-reports xunit-reports
