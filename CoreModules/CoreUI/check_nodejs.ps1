# Script to check if Node.js is installed and help with setup

Write-Host "Checking for Node.js installation..." -ForegroundColor Cyan

# Check common installation paths
$nodePaths = @(
    "C:\Program Files\nodejs\node.exe",
    "C:\Program Files (x86)\nodejs\node.exe",
    "$env:APPDATA\npm\node.exe",
    "$env:LOCALAPPDATA\Programs\nodejs\node.exe"
)

$found = $false
foreach ($path in $nodePaths) {
    if (Test-Path $path) {
        Write-Host "Found Node.js at: $path" -ForegroundColor Green
        $found = $true
        
        # Try to get version
        try {
            $version = & $path --version
            Write-Host "Node.js version: $version" -ForegroundColor Green
        } catch {
            Write-Host "Could not get version" -ForegroundColor Yellow
        }
        break
    }
}

if (-not $found) {
    Write-Host "Node.js not found in common locations." -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Node.js from: https://nodejs.org/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add to PATH' during installation." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installation, restart your terminal and run this script again." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Checking if npm is available..." -ForegroundColor Cyan
    
    # Try to find npm
    $npmPaths = @(
        "C:\Program Files\nodejs\npm.cmd",
        "C:\Program Files (x86)\nodejs\npm.cmd",
        "$env:APPDATA\npm\npm.cmd"
    )
    
    $npmFound = $false
    foreach ($npmPath in $npmPaths) {
        if (Test-Path $npmPath) {
            Write-Host "Found npm at: $npmPath" -ForegroundColor Green
            $npmFound = $true
            break
        }
    }
    
    if (-not $npmFound) {
        Write-Host "npm not found. Node.js may not be properly installed." -ForegroundColor Red
    } else {
        Write-Host ""
        Write-Host "Node.js and npm are ready!" -ForegroundColor Green
        Write-Host "You can now run: npm install" -ForegroundColor Green
    }
}

Write-Host ""
Read-Host "Press Enter to exit"

