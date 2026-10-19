#Requires -Version 5.1
<#
.SYNOPSIS
    PotatoGroup 本地开发环境一键启动(Windows / PowerShell 版)。

.DESCRIPTION
    对应 POSIX 脚本 scripts/dev.sh,行为保持一致:
      - 前置检查后端虚拟环境与前端依赖是否就绪;
      - 同时启动后端(uvicorn :8000)与前端(vite :5173);
      - 日志分别写入 .dev-logs/backend.log 与 .dev-logs/frontend.log;
      - 任一服务退出,或按 Ctrl+C,则两个服务一起停止。

    兼容 Windows PowerShell 5.1 与 PowerShell 7+。

.PARAMETER NoReload
    后端不开启 --reload(默认开启,改代码自动重载)。

.PARAMETER BackendOnly
    只启动后端(前端未安装依赖时可用)。

.PARAMETER FrontendOnly
    只启动前端(后端已在别处运行时可用)。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -NoReload
#>
[CmdletBinding()]
param(
    [switch]$NoReload,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = 'Stop'

# ---------- 路径(相对脚本自身定位,支持从任意目录调用) ----------
$RootDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir 'backend'
$FrontendDir = Join-Path $RootDir 'frontend'
$LogDir = Join-Path $RootDir '.dev-logs'
$BackendLog = Join-Path $LogDir 'backend.log'
$FrontendLog = Join-Path $LogDir 'frontend.log'

$Python = Join-Path $BackendDir '.venv\Scripts\python.exe'
$EnvFile = Join-Path $BackendDir '.env'
$EnvExample = Join-Path $BackendDir '.env.example'
$NodeModules = Join-Path $FrontendDir 'node_modules'

$BackendPort = 8000
$FrontendPort = 5173

function Write-Info { param([string]$Message) Write-Host "[dev] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[dev] $Message" -ForegroundColor Yellow }
function Write-Fail {
    param([string]$Message)
    Write-Host "[dev] 失败: $Message" -ForegroundColor Red
    exit 1
}

function Test-PortInUse {
    param([int]$Port)
    try {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { return $true }
    }
    catch {
        # 回退:解析 netstat 输出
        $hit = netstat -ano -p TCP 2>$null | Select-String -Pattern ":$Port\s+\S+\s+LISTENING"
        if ($hit) { return $true }
    }
    return $false
}

function Get-PortOwnerProcessId {
    <# 返回监听指定端口的进程 Id 列表。 #>
    param([int]$Port)
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conns) { return @($conns | Select-Object -ExpandProperty OwningProcess -Unique) }
    }
    catch {
        # 回退:解析 netstat 输出(最后一列为 PID)
        $ids = @()
        foreach ($line in (netstat -ano -p TCP 2>$null | Select-String -Pattern ":$Port\s+\S+\s+LISTENING")) {
            $parts = ($line.ToString() -split '\s+') | Where-Object { $_ }
            if ($parts.Count -ge 1) { $ids += [int]$parts[-1] }
        }
        return @($ids | Select-Object -Unique)
    }
    return @()
}

function Get-OrphanChildProcessId {
    <# 查找"父进程已死"的孤儿子进程。
       uvicorn --reload 在 Windows 上用 multiprocessing 派生真正的 server,
       子进程命令行形如:
         python -c "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=1904, ...)"
       父进程被终止后,子进程仍持有监听套接字,但 TCP 表里记录的仍是已死的父 PID,
       按端口反查会拿到死 PID,因此只能靠命令行里的 parent_pid= 反查。 #>
    param([int]$ParentId)
    $result = @()
    try {
        $result = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.CommandLine -and $_.CommandLine -match "parent_pid=$ParentId\b" } |
            Select-Object -ExpandProperty ProcessId
    }
    catch {
        return @()
    }
    return @($result)
}

function Get-ChildProcessId {
    <# 返回指定进程的全部后代进程 Id。uvicorn --reload 会派生子进程,
       直接杀父进程会留下孤儿,故需整棵树终止。 #>
    param([int]$ParentId)
    $all = @()
    try {
        $all = Get-CimInstance Win32_Process -ErrorAction Stop |
            Select-Object ProcessId, ParentProcessId
    }
    catch {
        return @()
    }
    $result = New-Object System.Collections.ArrayList
    $queue = New-Object System.Collections.Queue
    $queue.Enqueue($ParentId)
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        foreach ($p in $all) {
            if ($p.ParentProcessId -eq $current) {
                [void]$result.Add([int]$p.ProcessId)
                $queue.Enqueue([int]$p.ProcessId)
            }
        }
    }
    return $result.ToArray()
}

function Stop-ProcessTree {
    <# 先杀后代再杀自身:父进程被强杀后其子进程会成为孤儿,
       此后无法再由 ParentProcessId 追溯,故必须自顶向下处理。 #>
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return }
    $childIds = Get-ChildProcessId -ParentId $ProcessId
    foreach ($childId in $childIds) {
        Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Test-ProcessAlive {
    param($Process)
    if ($null -eq $Process) { return $false }
    try { return -not $Process.HasExited }
    catch { return $false }
}

# ---------- 1. 前置检查 ----------
Write-Info '检查环境...'

$needBackend = -not $FrontendOnly
$needFrontend = -not $BackendOnly

if ($needBackend) {
    if (-not (Test-Path $Python)) {
        Write-Fail "后端虚拟环境未就绪,缺少:$Python`n        请先运行: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
    }
    if (-not (Test-Path $EnvFile)) {
        if (Test-Path $EnvExample) {
            Write-Warn 'backend/.env 不存在,正在从 .env.example 生成(本地默认 SQLite)'
            Copy-Item $EnvExample $EnvFile
        }
        else {
            Write-Fail '缺少 backend/.env 与 backend/.env.example'
        }
    }
    if (Test-PortInUse -Port $BackendPort) {
        Write-Fail "端口 $BackendPort 已被占用,请先停止占用进程:`n        Get-NetTCPConnection -LocalPort $BackendPort -State Listen | Select-Object OwningProcess"
    }
}

if ($needFrontend) {
    if (-not (Test-Path $NodeModules)) {
        Write-Fail "前端依赖未安装,缺少:$NodeModules`n        请先运行: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
    }
    if (Test-PortInUse -Port $FrontendPort) {
        Write-Fail "端口 $FrontendPort 已被占用,请先停止占用进程"
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Fail '未找到 npm,请确认 Node.js 已安装并在 PATH 中'
    }
}

$null = New-Item -ItemType Directory -Path $LogDir -Force

# ---------- 2. 启动 ----------
$BackendProc = $null
$FrontendProc = $null

function Stop-All {
    Write-Host ''
    Write-Info '正在停止所有服务...'

    # 第一轮:终止我们亲自启动的进程树
    foreach ($proc in @($FrontendProc, $BackendProc)) {
        if (-not (Test-ProcessAlive -Process $proc)) { continue }
        $pidToKill = $proc.Id
        try {
            Stop-ProcessTree -ProcessId $pidToKill
        }
        catch {
            Write-Warn "停止进程 $pidToKill 时出现问题: $($_.Exception.Message)"
        }
    }

    # 第二轮:按端口兜底清理,并回收孤儿子进程。
    # uvicorn --reload 的父进程只是监督者,真正的 server 是 multiprocessing 子进程;
    # 父进程一旦消失,孤儿进程无法再由 ParentProcessId 追溯,需从命令行 parent_pid= 反查。
    $sweepTargets = New-Object System.Collections.ArrayList
    foreach ($port in @($BackendPort, $FrontendPort)) {
        try {
            foreach ($portPid in (Get-PortOwnerProcessId -Port $port)) {
                if ($portPid -gt 0) { [void]$sweepTargets.Add([int]$portPid) }
            }
        }
        catch {
            Write-Warn "清理端口 $port 时出现问题: $($_.Exception.Message)"
        }
    }
    foreach ($proc in @($FrontendProc, $BackendProc)) {
        if ($null -eq $proc) { continue }
        try {
            foreach ($orphanId in (Get-OrphanChildProcessId -ParentId $proc.Id)) {
                [void]$sweepTargets.Add([int]$orphanId)
            }
        }
        catch {
            # 孤儿回收失败不应影响其余清理
        }
    }

    foreach ($targetId in ($sweepTargets | Select-Object -Unique)) {
        if ($targetId -le 0 -or $targetId -eq $PID) { continue }
        try {
            Stop-ProcessTree -ProcessId ([int]$targetId)
        }
        catch {
            Write-Warn "清理进程 $targetId 时出现问题: $($_.Exception.Message)"
        }
    }

    # 第三轮:确认端口确实释放
    Start-Sleep -Milliseconds 800
    foreach ($port in @($BackendPort, $FrontendPort)) {
        if (Test-PortInUse -Port $port) {
            Write-Warn "端口 $port 仍被占用,可能需要在任务管理器中手动结束相关进程"
        }
    }

    Write-Info '已全部停止'
}

try {
    if ($needBackend) {
        Write-Info "启动后端(uvicorn, http://127.0.0.1:$BackendPort)..."
        $uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--port', "$BackendPort")
        if (-not $NoReload) { $uvicornArgs += '--reload' }
        $BackendProc = Start-Process -FilePath $Python -ArgumentList $uvicornArgs `
            -WorkingDirectory $BackendDir -PassThru -NoNewWindow `
            -RedirectStandardOutput $BackendLog -RedirectStandardError "$BackendLog.err"
    }

    if ($needFrontend) {
        Write-Info "启动前端(vite, http://localhost:$FrontendPort)..."
        # npm 是 .cmd 批处理,须经 cmd.exe 启动
        $FrontendProc = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npm', 'run', 'dev' `
            -WorkingDirectory $FrontendDir -PassThru -NoNewWindow `
            -RedirectStandardOutput $FrontendLog -RedirectStandardError "$FrontendLog.err"
    }

    Write-Host ''
    Write-Info '两个服务已启动,按 Ctrl+C 退出'
    if ($needFrontend) { Write-Info "前端页面  http://localhost:$FrontendPort" }
    if ($needBackend) { Write-Info "API 文档  http://127.0.0.1:$BackendPort/docs" }
    Write-Info "日志目录  $LogDir"
    Write-Host ''

    # ---------- 3. 等待:任一服务退出即整体结束 ----------
    $pending = @()
    if ($null -ne $BackendProc) { $pending += $BackendProc }
    if ($null -ne $FrontendProc) { $pending += $FrontendProc }

    try {
        while ($true) {
            foreach ($proc in $pending) {
                if (-not (Test-ProcessAlive -Process $proc)) {
                    Write-Warn "检测到服务退出(PID $($proc.Id)),正在清理..."
                    throw [System.OperationCanceledException]::new('service exited')
                }
            }
            Start-Sleep -Milliseconds 500
        }
    }
    catch [System.OperationCanceledException] {
        # 正常退出路径:某个服务自己停了
    }
}
finally {
    Stop-All
}
