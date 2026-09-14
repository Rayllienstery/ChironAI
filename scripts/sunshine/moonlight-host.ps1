<#
.SYNOPSIS
  Moonlight / Sunshine quick-menu actions.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('cursor', 'cursor-agents', 'playnite', 'playnite-close', 'youtube', 'youtube-close', 'brave', 'brave-close', 'sleep', 'restart-docker', 'restart-chironai', 'restart-pc')]
    [string]$Action = 'cursor',
    [int]$DelaySeconds = -1,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path

function Get-HostPort {
    foreach ($name in @('CHIRONAI_PHONE_STATUS_PORT', 'CHIRONAI_ACTIVE_SERVER_PORT', 'SERVER_PORT')) {
        $raw = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($raw)) {
            $parsed = 0
            if ([int]::TryParse($raw, [ref]$parsed) -and $parsed -ge 1 -and $parsed -le 65535) {
                return $parsed
            }
        }
    }
    return 8080
}

function Test-ChironGenerating {
    $port = Get-HostPort
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/webui/host/phone-status" -Method Get -TimeoutSec 3
    } catch {
        return $null
    }
    if ($status -and $status.generating) {
        return $status
    }
    return $null
}

function Show-Notice([string]$Title, [string]$Message, [string]$Icon = 'Information') {
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::$Icon
    ) | Out-Null
}

function Assert-NotGenerating([string]$ActionLabel) {
    if ($Force) { return }
    $status = Test-ChironGenerating
    if ($null -eq $status) { return }
    $detail = [string]$status.detail
    $msg = if ($detail) {
        "$ActionLabel blocked: PC is generating ($detail)."
    } else {
        "$ActionLabel blocked: PC is generating."
    }
    Write-Output $msg
    Show-Notice 'Moonlight' $msg 'Warning'
    exit 10
}

function Get-CursorExe {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'cursor\Cursor.exe'),
        (Join-Path ${env:ProgramFiles} 'Cursor\Cursor.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\cursor\Cursor.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Cursor\Cursor.exe')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    throw 'Cursor.exe was not found. Install Cursor or update scripts/sunshine.'
}

function Get-PlayniteDir {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Playnite'),
        (Join-Path ${env:ProgramFiles} 'Playnite'),
        (Join-Path ${env:ProgramFiles(x86)} 'Playnite')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath (Join-Path $path 'Playnite.FullscreenApp.exe'))) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    throw 'Playnite was not found. Install Playnite or re-run scripts/sunshine/install-apps.ps1.'
}

function Get-PlayniteExe([string]$Name) {
    $exe = Join-Path (Get-PlayniteDir) $Name
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "$Name was not found in the Playnite install folder."
    }
    return $exe
}

function Get-PlayniteProcesses {
    return @(Get-Process -Name @('Playnite.FullscreenApp', 'Playnite.DesktopApp', 'Playnite') -ErrorAction SilentlyContinue)
}

function Stop-Playnite {
    $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        foreach ($image in @('Playnite.FullscreenApp.exe', 'Playnite.DesktopApp.exe')) {
            & $taskkill /F /IM $image /T 2>$null | Out-Null
        }
        Get-PlayniteProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 200
        Get-PlayniteProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    } finally {
        $ErrorActionPreference = $prev
    }
    $left = @(Get-PlayniteProcesses)
    if ($left.Count -gt 0) {
        Write-Output ("PLAYNITE_CLOSE_LEFT " + (($left | ForEach-Object { $_.ProcessName }) -join ','))
        return
    }
    Write-Output 'PLAYNITE_CLOSE_OK'
}

function Get-SunshineLogPath {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'Sunshine\config\sunshine.log'),
        (Join-Path ${env:ProgramFiles(x86)} 'Sunshine\config\sunshine.log')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return $path
        }
    }
    return $null
}

function Get-SunshineLogStamp([string]$Needle) {
    $path = Get-SunshineLogPath
    if (-not $path) { return $null }
    $latest = $null
    $lines = @(Get-Content -LiteralPath $path -Tail 200 -ErrorAction SilentlyContinue)
    foreach ($line in $lines) {
        if ($line -notlike "*${Needle}*") { continue }
        if ($line -notmatch '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)') { continue }
        try {
            $stamp = [datetime]::Parse($Matches[1], [cultureinfo]::InvariantCulture)
        } catch {
            continue
        }
        if ($null -eq $latest -or $stamp -gt $latest) {
            $latest = $stamp
        }
    }
    return $latest
}

function Wait-PlayniteUntilStreamEnds([datetime]$StartedAt) {
    $connectedAt = $null
    $saw = $false
    $deadline = $StartedAt.AddHours(6)
    while ((Get-Date) -lt $deadline) {
        if ((Get-PlayniteProcesses).Count -gt 0) {
            $saw = $true
        } elseif ($saw) {
            Write-Output 'Playnite already exited'
            return
        }
        $conn = Get-SunshineLogStamp 'CLIENT CONNECTED'
        if ($conn -and $conn -gt $StartedAt) {
            $connectedAt = $conn
        }
        $disc = Get-SunshineLogStamp 'CLIENT DISCONNECTED'
        if ($connectedAt -and $disc -and $disc -gt $connectedAt) {
            Write-Output 'Moonlight stream ended; closing Playnite'
            Stop-Playnite
            return
        }
        Start-Sleep -Milliseconds 200
    }
}

function Initialize-Win32Window {
    if ('Win32Window' -as [type]) { return }
    Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class Win32Window {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
}
"@
}

function Get-VisibleWindowTitles {
    Initialize-Win32Window
    $script:Win32WindowTitles = New-Object System.Collections.Generic.List[string]
    $cb = [Win32Window+EnumProc] {
        param($hWnd, $lParam)
        if (-not [Win32Window]::IsWindowVisible($hWnd)) { return $true }
        $sb = New-Object System.Text.StringBuilder 512
        [void][Win32Window]::GetWindowText($hWnd, $sb, $sb.Capacity)
        $title = $sb.ToString()
        if (-not [string]::IsNullOrWhiteSpace($title)) {
            $script:Win32WindowTitles.Add($title)
        }
        return $true
    }
    [Win32Window]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return @($script:Win32WindowTitles)
}

function Close-WindowsMatchingTitle([scriptblock]$Predicate) {
    Initialize-Win32Window
    $script:closed = 0
    $cb = [Win32Window+EnumProc] {
        param($hWnd, $lParam)
        if (-not [Win32Window]::IsWindowVisible($hWnd)) { return $true }
        $sb = New-Object System.Text.StringBuilder 512
        [void][Win32Window]::GetWindowText($hWnd, $sb, $sb.Capacity)
        $title = $sb.ToString()
        if (& $Predicate $title) {
            [void][Win32Window]::PostMessage($hWnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
            $script:closed++
        }
        return $true
    }
    [Win32Window]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return [int]$script:closed
}

function Test-IsYouTubeWindowTitle([string]$Title) {
    if ([string]::IsNullOrWhiteSpace($Title)) { return $false }
    if ($Title -eq 'YouTube') { return $true }
    if ($Title.EndsWith(' - YouTube Music')) { return $false }
    return $Title.EndsWith(' - YouTube')
}

function Test-IsBraveBrowserWindowTitle([string]$Title) {
    if ([string]::IsNullOrWhiteSpace($Title)) { return $false }
    if ($Title -eq 'Brave') { return $true }
    return $Title.EndsWith(' - Brave') -or $Title.EndsWith(' - Brave Beta') -or $Title.EndsWith(' - Brave Nightly')
}

function Get-BraveDir {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'BraveSoftware\Brave-Browser\Application'),
        (Join-Path ${env:ProgramFiles(x86)} 'BraveSoftware\Brave-Browser\Application'),
        (Join-Path $env:LOCALAPPDATA 'BraveSoftware\Brave-Browser\Application')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath (Join-Path $path 'brave.exe'))) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    throw 'Brave was not found. Install Brave Browser or update scripts/sunshine.'
}

function Get-BraveExe {
    return (Join-Path (Get-BraveDir) 'brave.exe')
}

function Get-BraveProxyExe {
    $proxy = Join-Path (Get-BraveDir) 'chrome_proxy.exe'
    if (Test-Path -LiteralPath $proxy) { return $proxy }
    return Get-BraveExe
}

function Split-LaunchArgs([string]$Raw) {
    if ([string]::IsNullOrWhiteSpace($Raw)) { return @() }
    $matches = [regex]::Matches($Raw, '(?:"[^"]+"|[^\s]+)')
    $args = @()
    foreach ($match in $matches) {
        $args += $match.Value.Trim('"')
    }
    return $args
}

function Get-BraveYouTubeLaunch {
    $lnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Brave Apps\YouTube.lnk'
    $exe = Get-BraveProxyExe
    $work = Get-BraveDir
    $args = @('--profile-directory=Default', '--app-id=agimnkijcaahngcdmfeangaknmldooml')
    if (Test-Path -LiteralPath $lnk) {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($lnk)
        if ($shortcut.TargetPath -and (Test-Path -LiteralPath $shortcut.TargetPath)) {
            $exe = $shortcut.TargetPath
        }
        if ($shortcut.WorkingDirectory -and (Test-Path -LiteralPath $shortcut.WorkingDirectory)) {
            $work = $shortcut.WorkingDirectory
        }
        $fromLnk = Split-LaunchArgs $shortcut.Arguments
        if ($fromLnk.Count -gt 0) {
            $args = $fromLnk
        }
    }
    if ($args -notcontains '--start-maximized') {
        $args += '--start-maximized'
    }
    return @{ Exe = $exe; Args = $args; Work = $work }
}

function Wait-WindowsGone([scriptblock]$Predicate, [int]$TimeoutMs = 2000) {
    $deadline = (Get-Date).AddMilliseconds($TimeoutMs)
    while ((Get-Date) -lt $deadline) {
        $left = @(Get-VisibleWindowTitles | Where-Object { & $Predicate $_ })
        if ($left.Count -eq 0) { return $true }
        Start-Sleep -Milliseconds 200
    }
    return $false
}

function Stop-YouTubeApp {
    $closed = Close-WindowsMatchingTitle { param($title) Test-IsYouTubeWindowTitle $title }
    if ($closed -eq 0) {
        Write-Output 'YOUTUBE_CLOSE_OK already stopped'
        return
    }
    if (Wait-WindowsGone { param($title) Test-IsYouTubeWindowTitle $title }) {
        Write-Output "YOUTUBE_CLOSE_OK closed $closed"
        return
    }
    Write-Output "YOUTUBE_CLOSE_OK sent $closed"
}

function Stop-BraveBrowser {
    $closed = Close-WindowsMatchingTitle { param($title) Test-IsBraveBrowserWindowTitle $title }
    if ($closed -eq 0) {
        Write-Output 'BRAVE_CLOSE_OK already stopped'
        return
    }
    if (Wait-WindowsGone { param($title) Test-IsBraveBrowserWindowTitle $title }) {
        Write-Output "BRAVE_CLOSE_OK closed $closed"
        return
    }
    Write-Output "BRAVE_CLOSE_OK sent $closed"
}

function Get-DockerCli {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'Docker\Docker\resources\bin\docker.exe'),
        (Join-Path ${env:ProgramFiles} 'Docker\Docker\DockerCli.exe')
    )
    $cmd = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $candidates = @($cmd.Source) + $candidates
    }
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return $path
        }
    }
    throw 'docker.exe was not found. Install Docker Desktop.'
}

function Wait-Delay([int]$Seconds, [string]$Label) {
    if ($Seconds -lt 0) { return }
    if ($Seconds -eq 0) { return }
    Write-Output "$Label in $Seconds seconds..."
    Start-Sleep -Seconds $Seconds
}

function Initialize-ChironEnvironment {
    $env:PYTHONPATH = "$RepoRoot;$RepoRoot\Core;$RepoRoot\Core\modules\webui_backend;$env:PYTHONPATH"
    if (-not $env:HERMES_HOME -and (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'hermes'))) {
        $env:HERMES_HOME = Join-Path $env:LOCALAPPDATA 'hermes'
    }
}

function Wait-ChironReady([int]$TimeoutSec = 45) {
    $port = Get-HostPort
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $live = Invoke-RestMethod -Uri "http://127.0.0.1:$port/live" -Method Get -TimeoutSec 2
            if ($live) { return $true }
        } catch {
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

switch ($Action) {
    'cursor' {
        $exe = Get-CursorExe
        $work = Split-Path -Parent $exe
        Write-Output "Starting Cursor IDE: $exe --classic"
        Start-Process -FilePath $exe -ArgumentList @('--classic') -WorkingDirectory $work
        exit 0
    }
    'cursor-agents' {
        $exe = Get-CursorExe
        $work = Split-Path -Parent $exe
        Write-Output "Starting Cursor Agents: $exe --glass --new-window"
        Start-Process -FilePath $exe -ArgumentList @('--glass', '--new-window') -WorkingDirectory $work
        exit 0
    }
    'playnite' {
        $exe = Get-PlayniteExe 'Playnite.FullscreenApp.exe'
        $work = Split-Path -Parent $exe
        $startedAt = Get-Date
        Write-Output "Starting Playnite fullscreen: $exe --hidesplashscreen"
        Start-Process -FilePath $exe -ArgumentList @('--hidesplashscreen') -WorkingDirectory $work
        $deadline = (Get-Date).AddSeconds(20)
        while ((Get-Date) -lt $deadline) {
            if (Get-Process -Name 'Playnite.FullscreenApp' -ErrorAction SilentlyContinue) { break }
            Start-Sleep -Milliseconds 200
        }
        if (-not (Get-Process -Name 'Playnite.FullscreenApp' -ErrorAction SilentlyContinue)) {
            throw 'Playnite.FullscreenApp.exe did not start.'
        }
        Wait-PlayniteUntilStreamEnds $startedAt
        exit 0
    }
    'playnite-close' {
        Stop-Playnite
        exit 0
    }
    'youtube' {
        $launch = Get-BraveYouTubeLaunch
        Write-Output ("Starting YouTube app: {0} {1}" -f $launch.Exe, ($launch.Args -join ' '))
        Start-Process -FilePath $launch.Exe -ArgumentList $launch.Args -WorkingDirectory $launch.Work
        exit 0
    }
    'youtube-close' {
        Stop-YouTubeApp
        exit 0
    }
    'brave' {
        $exe = Get-BraveExe
        $work = Split-Path -Parent $exe
        Write-Output "Starting Brave: $exe --new-window --start-maximized"
        Start-Process -FilePath $exe -ArgumentList @('--new-window', '--start-maximized') -WorkingDirectory $work
        exit 0
    }
    'brave-close' {
        Stop-BraveBrowser
        exit 0
    }
    'sleep' {
        Add-Type -AssemblyName System.Windows.Forms | Out-Null
        Assert-NotGenerating 'Sleep'
        $seconds = if ($DelaySeconds -ge 0) { $DelaySeconds } else { 3 }
        Wait-Delay $seconds 'Sleep'
        Write-Output 'SLEEP_OK'
        [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false) | Out-Null
        exit 0
    }
    'restart-docker' {
        $seconds = if ($DelaySeconds -ge 0) { $DelaySeconds } else { 1 }
        Wait-Delay $seconds 'Docker restart'
        $docker = Get-DockerCli
        Write-Output "Restarting Docker Desktop via $docker"
        if ([IO.Path]::GetFileName($docker) -ieq 'DockerCli.exe') {
            & $docker -Shutdown
            $desktop = Join-Path ${env:ProgramFiles} 'Docker\Docker\Docker Desktop.exe'
            if (-not (Test-Path -LiteralPath $desktop)) {
                throw "Docker Desktop.exe not found at $desktop"
            }
            Start-Process -FilePath $desktop
        } else {
            & $docker desktop restart
            if ($LASTEXITCODE -ne 0) {
                throw "docker desktop restart failed with exit $LASTEXITCODE"
            }
        }
        Write-Output 'DOCKER_RESTART_OK'
        exit 0
    }
    'restart-chironai' {
        Assert-NotGenerating 'Restart ChironAI'
        $seconds = if ($DelaySeconds -ge 0) { $DelaySeconds } else { 1 }
        Wait-Delay $seconds 'ChironAI restart'
        Initialize-ChironEnvironment
        Write-Output "Stopping ChironAI listeners from $RepoRoot"
        Push-Location -LiteralPath $RepoRoot
        try {
            & python -m webui_backend.kill_listeners_on_config_port
            Start-Process -FilePath 'python' -ArgumentList @('-m', 'webui_backend.rag_proxy') -WorkingDirectory $RepoRoot -WindowStyle Minimized
        } finally {
            Pop-Location
        }
        if (Wait-ChironReady 45) {
            Write-Output 'CHIRONAI_RESTART_OK'
            exit 0
        }
        Write-Output 'CHIRONAI_RESTART_STARTED backend is still coming up'
        exit 0
    }
    'restart-pc' {
        Assert-NotGenerating 'Restart PC'
        $seconds = if ($DelaySeconds -ge 0) { $DelaySeconds } else { 5 }
        Wait-Delay $seconds 'PC restart'
        Write-Output 'RESTART_PC_OK'
        Start-Process -FilePath "$env:SystemRoot\System32\shutdown.exe" -ArgumentList @('/r', '/t', '0', '/d', 'p:0:0', '/c', 'Restart from Moonlight') -Wait
        exit 0
    }
}
