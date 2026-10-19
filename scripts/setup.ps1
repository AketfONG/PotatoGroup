#Requires -Version 5.1
<#
.SYNOPSIS
    PotatoGroup 本地环境一键初始化(Windows / PowerShell 版)。

.DESCRIPTION
    对应 POSIX 脚本 scripts/setup.sh,行为保持一致且幂等,可反复执行:
      1. 检查 Node.js / Python 版本;
      2. 创建后端虚拟环境 backend\.venv 并安装 requirements.txt;
      3. 若无 backend\.env 则从 .env.example 生成;
      4. 在 frontend\ 执行 npm ci 安装依赖(无 lockfile 时回退 npm install)。

    完成后用 scripts\dev.ps1 一键启动前后端。

.PARAMETER SkipFrontend
    只初始化后端,跳过前端依赖安装。

.PARAMETER Force
    即使虚拟环境已存在也重建(用于修复损坏的环境)。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir 'backend'
$FrontendDir = Join-Path $RootDir 'frontend'
$VenvDir = Join-Path $BackendDir '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$EnvFile = Join-Path $BackendDir '.env'
$EnvExample = Join-Path $BackendDir '.env.example'
$Requirements = Join-Path $BackendDir 'requirements.txt'

function Write-Info { param([string]$Message) Write-Host "[setup] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[setup] $Message" -ForegroundColor Yellow }
function Write-Fail {
    param([string]$Message)
    Write-Host "[setup] 失败: $Message" -ForegroundColor Red
    exit 1
}

# ---------- 1. 前置检查 ----------
Write-Info '检查依赖工具版本...'

# Node.js
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { Write-Fail '未找到 node,请先安装 Node.js 18+ (https://nodejs.org/ LTS)' }
# 注意:避免 `node -p "...split('.')..."` 这类嵌套引号写法,
# Windows PowerShell 5.1 调用原生命令时会吞掉内层引号导致 node 解析失败。
$nodeVersionText = (& node --version).Trim().TrimStart('v')
$nodeMajor = [int]($nodeVersionText -split '\.')[0]
if ($nodeMajor -lt 18) { Write-Fail "node 版本过低(当前 v$nodeVersionText),需要 18+" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Fail '未找到 npm,请随 Node.js 一并安装' }

# Python:依次尝试 python / py -3 / python3,取第一个满足 3.11+ 的
# (优先 python:与 backend/.venv 的创建来源保持一致)
function Find-Python {
    $candidates = @(
        @{ Exe = 'python'; Args = @() },
        @{ Exe = 'py'; Args = @('-3') },
        @{ Exe = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
        try {
            # 注意:Windows PowerShell 5.1 调用原生命令时会吞掉参数里的引号,
            # 所以用 chr(46) 代替 "." 拼版本号,否则会传成非法语法。
            $out = & $c.Exe @($c.Args) -c 'import sys; print(str(sys.version_info.major) + chr(46) + str(sys.version_info.minor))' 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $out) { continue }
            $verText = ($out | Select-Object -First 1).Trim()
            $parts = $verText -split '\.'
            if ($parts.Count -lt 2) { continue }
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) {
                return @{ Exe = $c.Exe; Args = $c.Args; Version = $verText }
            }
        }
        catch { continue }
    }
    return $null
}

$python = Find-Python
if (-not $python) { Write-Fail '未找到 Python 3.11+,请先安装 (https://www.python.org/downloads/)' }

Write-Info "工具检查通过: node v$nodeVersionText / python $($python.Version)"

# ---------- 2. 后端环境 ----------
Write-Info '配置后端 (backend/)...'

if ($Force -and (Test-Path $VenvDir)) {
    Write-Warn '指定了 -Force,正在删除已有虚拟环境...'
    Remove-Item $VenvDir -Recurse -Force
}

if (-not (Test-Path $VenvPython)) {
    Write-Info '创建虚拟环境 backend\.venv ...'
    & $python.Exe @($python.Args) -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Fail '创建虚拟环境失败' }
}
else {
    Write-Info '虚拟环境已存在,跳过创建(如需重建请加 -Force)'
}

Write-Info '安装后端 Python 依赖 (requirements.txt)...'
& $VenvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Fail '升级 pip 失败' }
& $VenvPython -m pip install --quiet -r $Requirements
if ($LASTEXITCODE -ne 0) { Write-Fail '安装后端依赖失败' }
Write-Info '后端依赖安装完成'

if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $EnvExample)) { Write-Fail '缺少 backend\.env.example,无法生成配置' }
    Write-Info '生成 backend\.env(基于 .env.example,请按需修改)'
    Copy-Item $EnvExample $EnvFile
    Write-Warn '默认使用 SQLite;切换 MySQL 请编辑 backend\.env 中的 DATABASE_URL'
}
else {
    Write-Info 'backend\.env 已存在,保持不动'
}

# SQLite 无需手动建库:首次启动时自动建表

# ---------- 3. 前端环境 ----------
if ($SkipFrontend) {
    Write-Info '已指定 -SkipFrontend,跳过前端依赖安装'
}
else {
    Write-Info '配置前端 (frontend/)...'
    Push-Location $FrontendDir
    try {
        if (Test-Path (Join-Path $FrontendDir 'package-lock.json')) {
            Write-Info '检测到 package-lock.json,使用 npm ci 保证依赖树与提交版本一致'
            & npm ci --silent
        }
        else {
            Write-Warn '未找到 package-lock.json,回退到 npm install(建议提交 lockfile)'
            & npm install --silent
        }
        if ($LASTEXITCODE -ne 0) { Write-Fail '安装前端依赖失败' }
    }
    finally {
        Pop-Location
    }
    Write-Info '前端依赖安装完成'
}

# ---------- 4. 完成 ----------
Write-Host ''
Write-Info '初始化完成!下一步:'
Write-Host '  ---------------------------------------------'
Write-Host '  1) 一键启动前后端:  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1'
Write-Host '     (或分开启动:'
Write-Host '       后端  cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000'
Write-Host '       前端  cd frontend; npm run dev)'
Write-Host '  2) 打开前端页面:    http://localhost:5173'
Write-Host '  3) 后端 API 文档:   http://127.0.0.1:8000/docs'
Write-Host '  ---------------------------------------------'
Write-Host '  本地默认使用 SQLite,数据文件 backend\potato.db(已被 gitignore)'
Write-Host '  首次使用请先在前端注册账号'
Write-Host ''
