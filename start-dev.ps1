# start-dev.ps1 — 星萌弹幕姬 本地一键启动脚本
# 用法：
#   powershell -ExecutionPolicy Bypass -File start-dev.ps1          # 正常启动
#   powershell -ExecutionPolicy Bypass -File start-dev.ps1 -CheckOnly  # 只做环境检查，不启动
# 可选参数：-NoOpen 不自动打开浏览器

param(
    [switch]$CheckOnly,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$server = Join-Path $root "server"
$web = Join-Path $root "web"

Write-Host ""
Write-Host "=== 星萌弹幕姬 本地开发环境检查 ===" -ForegroundColor Cyan

# ── 1. 基础工具检查 ──
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "[FAIL] 未找到 python，请先安装 Python 3.11+" -ForegroundColor Red; exit 1 }
Write-Host "[OK] python: $($py.Source)"

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) { Write-Host "[FAIL] 未找到 npm，请先安装 Node.js 18+" -ForegroundColor Red; exit 1 }
Write-Host "[OK] npm: $($npm.Source)"

# ── 2. 生成 .env（不存在时）──
$envFile = Join-Path $server ".env"
if (-not (Test-Path $envFile)) {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes)
    @"
CUTESTAR_ENV=development
CUTESTAR_DATABASE_URL=sqlite+aiosqlite:///./dev.db
CUTESTAR_REDIS_URL=
CUTESTAR_CORS_ORIGINS=http://localhost:5173
CUTESTAR_JWT_SECRET=$secret
CUTESTAR_ADMIN_USERNAME=admin
CUTESTAR_ADMIN_PASSWORD=admin123
CUTESTAR_ADMIN_ENTRY_PATH=dev-control-2026
"@ | Set-Content -Encoding UTF8 $envFile
    Write-Host "[OK] 已生成 $envFile（SQLite / admin / admin123）" -ForegroundColor Yellow
} else {
    Write-Host "[OK] .env 已存在"
}

$adminEntryLine = Get-Content $envFile | Where-Object { $_ -match '^CUTESTAR_ADMIN_ENTRY_PATH=' } | Select-Object -First 1
if (-not $adminEntryLine) {
    Add-Content -Encoding UTF8 $envFile "CUTESTAR_ADMIN_ENTRY_PATH=dev-control-2026"
    $adminEntry = "dev-control-2026"
    Write-Host "[OK] 已补充后台安全入口" -ForegroundColor Yellow
} else {
    $adminEntry = ($adminEntryLine -split '=', 2)[1].Trim()
}

# ── 3. 后端依赖检查 ──
Push-Location $server
try {
    python -c "import fastapi, uvicorn, sqlalchemy, aiosqlite" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[..] 安装后端依赖……" -ForegroundColor Yellow
        python -m pip install -r requirements.txt -r requirements-dev.txt
        if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 后端依赖安装失败" -ForegroundColor Red; exit 1 }
        Write-Host "[OK] 后端依赖已安装"
    } else {
        Write-Host "[OK] 后端依赖已就绪"
    }
} finally { Pop-Location }

# ── 4. 前端依赖检查 ──
if (-not (Test-Path (Join-Path $web "node_modules"))) {
    Write-Host "[..] 安装前端依赖（npm install）……" -ForegroundColor Yellow
    Push-Location $web
    try { npm install --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 前端依赖安装失败" -ForegroundColor Red; exit 1 } } finally { Pop-Location }
    Write-Host "[OK] 前端依赖已安装"
} else {
    Write-Host "[OK] 前端依赖已就绪"
}

# ── 5. 数据库初始化（不存在 dev.db 时播种）──
$dbFile = Join-Path $server "dev.db"
if (-not (Test-Path $dbFile)) {
    Write-Host "[..] 初始化数据库并创建演示活动……" -ForegroundColor Yellow
    Push-Location $server
    try { python -m app.seed; if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 数据库初始化失败" -ForegroundColor Red; exit 1 } } finally { Pop-Location }
    Write-Host "[OK] 数据库已初始化（演示活动 MEET2026）"
} else {
    Write-Host "[OK] 数据库已存在"
}

# ── 6. 端口检查 ──
foreach ($port in @(8000, 5173)) {
    $used = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($used) {
        Write-Host "[WARN] 端口 $port 已被占用（可能已有实例在运行）" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] 端口 $port 空闲"
    }
}

if ($CheckOnly) {
    Write-Host ""
    Write-Host "=== 环境检查完成，未启动服务（-CheckOnly）===" -ForegroundColor Cyan
    exit 0
}

# ── 7. 启动服务（各自独立窗口）──
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle='星萌弹幕姬 后端 (8000)'; Set-Location '$server'; uvicorn app.main:app --reload --port 8000"
)

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle='星萌弹幕姬 前端 (5173)'; Set-Location '$web'; npm run dev"
)

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "=== 已启动 ===" -ForegroundColor Cyan
Write-Host "  活动码入口 : http://localhost:5173/" -ForegroundColor Green
Write-Host "  参与者页面 : http://localhost:5173/e/MEET2026" -ForegroundColor Green
Write-Host "  运营控制台 : http://localhost:5173/$adminEntry" -ForegroundColor Green
Write-Host "  后端健康   : http://localhost:8000/health" -ForegroundColor Green
Write-Host "  管理员账号 : admin / admin123（见 server\.env）"
Write-Host ""
Write-Host "提示：两个服务分别在独立窗口运行，Ctrl+C 可单独停止。"

if (-not $NoOpen) {
    Start-Sleep -Seconds 3
    Start-Process "http://localhost:5173/e/MEET2026"
}
