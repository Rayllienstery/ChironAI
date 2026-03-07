# PowerShell script to install dependencies and build React app

Write-Host "Installing npm dependencies..." -ForegroundColor Cyan
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install dependencies. Please make sure Node.js and npm are installed." -ForegroundColor Red
    exit 1
}

Write-Host "Building production bundle..." -ForegroundColor Cyan
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed." -ForegroundColor Red
    exit 1
}

Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "The React app is now ready to be served by the Flask server." -ForegroundColor Green

