# 致壹 智能办公：Streamlit 常驻巡检脚本（一次性执行，由计划任务每分钟调用）
# 端口不通时以 WMI 分离启动 pythonw：无控制台，不随终端或本脚本退出而终止。
#
# 不写死本机 Python 路径，按以下顺序探测「能 import streamlit」的解释器：
#   1. 环境变量 FLOWMIND_PYTHON
#   2. 项目内 .venv\Scripts\python.exe / venv\Scripts\python.exe
#   3. PATH 中的 python.exe（自动跳过 Windows Store 占位程序）
#   4. %LOCALAPPDATA%\Programs\Python\Python3*\python.exe、C:\Python3*\python.exe
#   5. py -3 启动器
# 端口与监听地址可用环境变量覆盖：FLOWMIND_PORT（默认 8501）、FLOWMIND_HOST（默认 0.0.0.0）

$wd = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $wd

$port = if ($env:FLOWMIND_PORT) { [int]$env:FLOWMIND_PORT } else { 8501 }
$bindHost = if ($env:FLOWMIND_HOST) { $env:FLOWMIND_HOST } else { '0.0.0.0' }
$log = Join-Path $wd 'streamlit.err.log'

function Write-Log([string]$msg) {
    Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) -Encoding UTF8
}

function Test-Port {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $c.Connect('127.0.0.1', $port)
        return $true
    } catch {
        return $false
    } finally {
        $c.Close()
    }
}

function Test-Streamlit([string]$py) {
    & $py -c "import streamlit" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Get-PythonCandidates {
    $list = @()
    if ($env:FLOWMIND_PYTHON) { $list += $env:FLOWMIND_PYTHON }
    $list += @(
        (Join-Path $wd '.venv\Scripts\python.exe'),
        (Join-Path $wd 'venv\Scripts\python.exe')
    )
    $onPath = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($onPath -and $onPath -notmatch '\\WindowsApps\\') { $list += $onPath }
    $list += @(Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $list += @(Get-ChildItem 'C:\Python3*\python.exe' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $pyLauncher = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if ($pyLauncher) {
        $real = & $pyLauncher -3 -c "import sys; print(sys.executable)" 2>$null
        if ($real) { $list += $real.Trim() }
    }
    return $list | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
}

if (Test-Port) { return }

$python = $null
$found = @()
foreach ($c in Get-PythonCandidates) {
    $found += $c
    if (Test-Streamlit $c) { $python = $c; break }
}

if (-not $python) {
    if ($found.Count -eq 0) {
        Write-Log 'ERROR: 未找到 Python。请安装 Python 3.9+（勾选 Add to PATH），或设置环境变量 FLOWMIND_PYTHON 指向 python.exe。'
    } else {
        Write-Log ("ERROR: 已找到 Python 但无法导入 streamlit：{0}。请执行: `"{1}`" -m pip install -r requirements.txt" -f ($found -join '; '), $found[0])
    }
    return
}

# 优先用同目录的 pythonw.exe（无控制台窗口）
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
$launcher = if (Test-Path $pythonw) { $pythonw } else { $python }

$cmd = '"' + $launcher + '" -m streamlit run streamlit_app.py --server.port ' + $port +
       ' --server.address ' + $bindHost + ' --server.headless true --browser.gatherUsageStats false'
try {
    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = $cmd; CurrentDirectory = $wd} | Out-Null
    Write-Log "start streamlit: port=$port host=$bindHost python=$launcher"
} catch {
    Write-Log "ERROR: 启动失败：$($_.Exception.Message)"
}
