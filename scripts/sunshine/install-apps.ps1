<#
.SYNOPSIS
  Merge Cursor, Cursor Agents, Playnite, YouTube, Brave, Sleep, Docker/ChironAI/PC restart tiles into Sunshine.
#>
[CmdletBinding()]
param(
    [string]$SunshineAppsPath = '',
    [switch]$SkipReload,
    [switch]$WriteOnly,
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CoverDir = Join-Path $ScriptDir 'covers'
$HostCmd = Join-Path $ScriptDir 'moonlight-host.cmd'
$HostPs1 = Join-Path $ScriptDir 'moonlight-host.ps1'
$StreamDisplayPs1 = Join-Path $ScriptDir 'on-stream-display.ps1'
$BuildPy = Join-Path $ScriptDir 'build_apps.py'

if (-not (Test-Path -LiteralPath $HostCmd)) {
    throw "moonlight-host.cmd not found at $HostCmd"
}
if (-not (Test-Path -LiteralPath $HostPs1)) {
    throw "moonlight-host.ps1 not found at $HostPs1"
}
if (-not (Test-Path -LiteralPath $StreamDisplayPs1)) {
    throw "on-stream-display.ps1 not found at $StreamDisplayPs1"
}
if (-not (Test-Path -LiteralPath $BuildPy)) {
    throw "build_apps.py not found at $BuildPy"
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-SunshineConfPath {
    $default = Join-Path ${env:ProgramFiles} 'Sunshine\config\sunshine.conf'
    if (Test-Path -LiteralPath $default) { return $default }
    throw "Sunshine sunshine.conf not found at $default"
}

function Get-GlobalPrepCmdJson {
    $do = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$StreamDisplayPs1`" -Action start"
    $undo = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$StreamDisplayPs1`" -Action stop"
    $obj = @(
        [ordered]@{
            do = $do
            undo = $undo
            elevated = $false
        }
    )
    return (ConvertTo-Json -InputObject $obj -Compress -Depth 5)
}

function Set-SunshineGlobalPrepCmd([string]$ConfPath) {
    $prepJson = Get-GlobalPrepCmdJson
    $line = "global_prep_cmd = $prepJson"
    $raw = ''
    if (Test-Path -LiteralPath $ConfPath) {
        $raw = Get-Content -LiteralPath $ConfPath -Raw -ErrorAction SilentlyContinue
        if ($null -eq $raw) { $raw = '' }
    }
    if ($raw -match '(?m)^\s*global_prep_cmd\s*=') {
        $raw = [regex]::Replace($raw, '(?m)^\s*global_prep_cmd\s*=.*$', $line)
    } else {
        if ($raw.Length -gt 0 -and -not $raw.EndsWith("`n")) {
            $raw += "`r`n"
        }
        $raw += $line + "`r`n"
    }
    [System.IO.File]::WriteAllText($ConfPath, $raw, (New-Object System.Text.UTF8Encoding $false))
    Write-Output "Wrote global_prep_cmd to $ConfPath"
}

function Get-SunshineAppsPath {
    if ($SunshineAppsPath) { return $SunshineAppsPath }
    $default = Join-Path ${env:ProgramFiles} 'Sunshine\config\apps.json'
    if (Test-Path -LiteralPath $default) { return $default }
    throw "Sunshine apps.json not found at $default"
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
    throw 'Cursor.exe was not found.'
}

function Get-PlayniteFullscreenExe {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Playnite\Playnite.FullscreenApp.exe'),
        (Join-Path ${env:ProgramFiles} 'Playnite\Playnite.FullscreenApp.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Playnite\Playnite.FullscreenApp.exe')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    return $null
}

function Get-BraveExe {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'BraveSoftware\Brave-Browser\Application\brave.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'BraveSoftware\Brave-Browser\Application\brave.exe'),
        (Join-Path $env:LOCALAPPDATA 'BraveSoftware\Brave-Browser\Application\brave.exe')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    return $null
}

function Get-YouTubeAppIcon {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'BraveSoftware\Brave-Browser\User Data\Default\Web Applications\_crx_agimnkijcaahngcdmfeangaknmldooml\YouTube.ico'),
        (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Brave Apps\YouTube.lnk')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return $path
        }
    }
    return $null
}

function Get-Python {
    foreach ($name in @('python', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    throw 'Python was not found on PATH.'
}

function Get-IconFont {
    foreach ($name in @('Segoe Fluent Icons', 'Segoe MDL2 Assets')) {
        try {
            $font = New-Object System.Drawing.Font $name, 180, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
            if ($font.Name -eq $name) {
                return $font
            }
            $font.Dispose()
        } catch {
        }
    }
    return $null
}

function Get-SourceBitmap([string]$Path, [int]$PreferredSize = 256) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $ext = [IO.Path]::GetExtension($Path)
    if ($ext -ieq '.ico') {
        $icon = New-Object System.Drawing.Icon $Path, $PreferredSize, $PreferredSize
        $bmp = $icon.ToBitmap()
        $icon.Dispose()
        return $bmp
    }
    if ($ext -ieq '.exe' -or $ext -ieq '.dll' -or $ext -ieq '.lnk') {
        $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($Path)
        if (-not $icon) { return $null }
        $bmp = $icon.ToBitmap()
        $icon.Dispose()
        return $bmp
    }
    $img = [System.Drawing.Image]::FromFile($Path)
    $clone = New-Object System.Drawing.Bitmap $img
    $img.Dispose()
    return $clone
}

function New-AppCover {
    param(
        [string]$Path,
        [string]$Source = '',
        [int]$BgR = 18,
        [int]$BgG = 20,
        [int]$BgB = 26,
        [string]$Glyph = '',
        [int]$GlyphR = 255,
        [int]$GlyphG = 255,
        [int]$GlyphB = 255,
        [string]$BadgeGlyph = ''
    )
    Add-Type -AssemblyName System.Drawing | Out-Null
    $width = 600
    $height = 800
    $bmp = New-Object System.Drawing.Bitmap $width, $height
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.Clear([System.Drawing.Color]::FromArgb($BgR, $BgG, $BgB))
    $iconBox = 320
    $x = [int](($width - $iconBox) / 2)
    $y = [int](($height - $iconBox) / 2) - 20
    $sourceBmp = $null
    if ($Source) {
        $sourceBmp = Get-SourceBitmap $Source
    }
    if ($sourceBmp) {
        $graphics.DrawImage($sourceBmp, $x, $y, $iconBox, $iconBox)
        $sourceBmp.Dispose()
    } elseif ($Glyph) {
        $font = Get-IconFont
        if ($font) {
            $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb($GlyphR, $GlyphG, $GlyphB))
            $format = New-Object System.Drawing.StringFormat
            $format.Alignment = [System.Drawing.StringAlignment]::Center
            $format.LineAlignment = [System.Drawing.StringAlignment]::Center
            $rect = New-Object System.Drawing.RectangleF 0, 0, $width, $height
            $graphics.DrawString($Glyph, $font, $brush, $rect, $format)
            $brush.Dispose()
            $font.Dispose()
        }
    }
    if ($BadgeGlyph) {
        $badgeFont = Get-IconFont
        if ($badgeFont) {
            $small = New-Object System.Drawing.Font $badgeFont.FontFamily, 92, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
            $badgeBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(88, 196, 220))
            $graphics.DrawString($BadgeGlyph, $small, $badgeBrush, 360, 470)
            $badgeBrush.Dispose()
            $small.Dispose()
            $badgeFont.Dispose()
        }
    }
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
    $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bmp.Dispose()
}

$cursorExe = Get-CursorExe
$cursorIco = Join-Path ${env:ProgramFiles} 'cursor\resources\app\resources\win32\code.ico'
if (-not (Test-Path -LiteralPath $cursorIco)) {
    $cursorIco = $cursorExe
}
$dockerPng = Join-Path ${env:ProgramFiles} 'Docker\Docker\frontend\resources\assets\app\icon.png'
$chironPng = Join-Path $ScriptDir '..\..\CoreModules\CoreUI\public\favicon-512.png'
New-Item -ItemType Directory -Path $CoverDir -Force | Out-Null
Get-ChildItem -LiteralPath $CoverDir -Filter '_probe-*' -ErrorAction SilentlyContinue | Remove-Item -Force
$cursorCover = Join-Path $CoverDir 'cursor.png'
$agentsCover = Join-Path $CoverDir 'cursor-agents.png'
$sleepCover = Join-Path $CoverDir 'sleep.png'
$dockerCover = Join-Path $CoverDir 'restart-docker.png'
$chironCover = Join-Path $CoverDir 'restart-chironai.png'
$rebootCover = Join-Path $CoverDir 'restart-pc.png'
$playniteCover = Join-Path $CoverDir 'playnite.png'
$youtubeCover = Join-Path $CoverDir 'youtube.png'
$braveCover = Join-Path $CoverDir 'brave.png'
$playniteExe = Get-PlayniteFullscreenExe
$braveExe = Get-BraveExe
$youtubeIcon = Get-YouTubeAppIcon
New-AppCover -Path $cursorCover -Source $cursorIco -BgR 10 -BgG 10 -BgB 12
New-AppCover -Path $agentsCover -Source $cursorIco -BgR 12 -BgG 16 -BgB 28 -BadgeGlyph ([char]0xE8BD)
New-AppCover -Path $sleepCover -BgR 18 -BgG 14 -BgB 32 -Glyph ([char]0xE708) -GlyphR 176 -GlyphG 148 -GlyphB 255
if (Test-Path -LiteralPath $dockerPng) {
    New-AppCover -Path $dockerCover -Source $dockerPng -BgR 8 -BgG 14 -BgB 24
} else {
    New-AppCover -Path $dockerCover -BgR 8 -BgG 14 -BgB 24 -Glyph ([char]0xE8FC) -GlyphR 41 -GlyphG 182 -GlyphB 246
}
if (Test-Path -LiteralPath $chironPng) {
    New-AppCover -Path $chironCover -Source $chironPng -BgR 24 -BgG 22 -BgB 20
} else {
    New-AppCover -Path $chironCover -BgR 24 -BgG 22 -BgB 20 -Glyph ([char]0xE7F4) -GlyphR 255 -GlyphG 176 -GlyphB 64
}
New-AppCover -Path $rebootCover -BgR 28 -BgG 12 -BgB 12 -Glyph ([char]0xE72C) -GlyphR 255 -GlyphG 96 -GlyphB 96
if ($playniteExe) {
    New-AppCover -Path $playniteCover -Source $playniteExe -BgR 8 -BgG 18 -BgB 28
} else {
    Write-Output 'Playnite was not found; skipping the Moonlight Playnite tile.'
}
if ($braveExe) {
    if ($youtubeIcon) {
        New-AppCover -Path $youtubeCover -Source $youtubeIcon -BgR 24 -BgG 8 -BgB 8
    } else {
        New-AppCover -Path $youtubeCover -BgR 24 -BgG 8 -BgB 8 -Glyph ([char]0xE714) -GlyphR 255 -GlyphG 64 -GlyphB 64
    }
    New-AppCover -Path $braveCover -Source $braveExe -BgR 28 -BgG 12 -BgB 8
} else {
    Write-Output 'Brave was not found; skipping the Moonlight YouTube and Brave tiles.'
}

$dest = Get-SunshineAppsPath
$tmp = Join-Path $env:TEMP 'sunshine-apps.moonlight.json'
$python = Get-Python
$pyArgs = @(
    $BuildPy,
    '--existing', $dest,
    '--out', $tmp,
    '--host-ps1', $HostPs1,
    '--working-dir', $ScriptDir,
    '--cursor-cover', $cursorCover,
    '--agents-cover', $agentsCover,
    '--sleep-cover', $sleepCover,
    '--docker-cover', $dockerCover,
    '--chiron-cover', $chironCover,
    '--reboot-cover', $rebootCover
)
if ($playniteExe) {
    $pyArgs += @('--playnite-cover', $playniteCover, '--playnite-exe', $playniteExe)
}
if ($braveExe) {
    $pyArgs += @('--youtube-cover', $youtubeCover, '--brave-cover', $braveCover)
}
& $python @pyArgs
if ($LASTEXITCODE -ne 0) {
    throw "build_apps.py failed with exit $LASTEXITCODE"
}

Copy-Item -LiteralPath $tmp -Destination (Join-Path $ScriptDir 'apps.json') -Force

if ($WriteOnly) {
    Get-Content -LiteralPath $tmp -Raw -Encoding UTF8
    exit 0
}

function Install-SunshineAppsFile {
    Copy-Item -LiteralPath $tmp -Destination $dest -Force
    Write-Output "Wrote $dest"
    $conf = Get-SunshineConfPath
    Set-SunshineGlobalPrepCmd $conf
    if ($SkipReload) { return }
    $sunshine = Get-Process -Name sunshine -ErrorAction SilentlyContinue
    if ($sunshine) {
        Stop-Process -Id $sunshine.Id -Force
        Write-Output 'Restarted Sunshine to reload apps + global_prep_cmd.'
    } else {
        Write-Output 'Sunshine process not running; config will load on next start.'
    }
}

if (Test-IsAdministrator) {
    Install-SunshineAppsFile
    exit 0
}

if ($Elevated) {
    throw 'Administrator rights are required to write Sunshine apps.json.'
}

$doReload = if ($SkipReload) { '$false' } else { '$true' }
$confPath = Get-SunshineConfPath
$prepLine = Get-GlobalPrepCmdJson
$helper = Join-Path $env:TEMP 'sunshine-install-copy.ps1'
$helperBody = @"
`$ErrorActionPreference = 'Stop'
Copy-Item -LiteralPath '$tmp' -Destination '$dest' -Force
`$conf = '$confPath'
`$line = 'global_prep_cmd = $prepLine'
`$raw = ''
if (Test-Path -LiteralPath `$conf) {
    `$raw = Get-Content -LiteralPath `$conf -Raw -ErrorAction SilentlyContinue
    if (`$null -eq `$raw) { `$raw = '' }
}
if (`$raw -match '(?m)^\s*global_prep_cmd\s*=') {
    `$raw = [regex]::Replace(`$raw, '(?m)^\s*global_prep_cmd\s*=.*`$', `$line)
} else {
    if (`$raw.Length -gt 0 -and -not `$raw.EndsWith([string][char]10)) { `$raw += "`r`n" }
    `$raw += `$line + "`r`n"
}
[System.IO.File]::WriteAllText(`$conf, `$raw, (New-Object System.Text.UTF8Encoding `$false))
if ($doReload) {
    Get-Process -Name sunshine -ErrorAction SilentlyContinue | Stop-Process -Force
}
"@
[System.IO.File]::WriteAllText($helper, $helperBody, (New-Object System.Text.UTF8Encoding $false))
Write-Output 'Windows will ask for Administrator permission to update Sunshine config. Click Yes.'
$proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -WindowStyle Normal -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $helper)
if ($null -eq $proc) {
    throw 'UAC elevation was cancelled.'
}
if ($proc.ExitCode -ne 0) {
    throw "Elevated copy failed with exit $($proc.ExitCode)"
}
Write-Output "Wrote $dest"
Write-Output "Wrote global_prep_cmd to $confPath"
if (-not $SkipReload) {
    Write-Output 'Sunshine reloaded.'
}
