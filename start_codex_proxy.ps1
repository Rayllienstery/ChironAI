param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$defaultBaseUrl = "http://127.0.0.1:8080"
if ([string]::IsNullOrWhiteSpace($env:CHIRON_PROXY_BASE_URL)) {
    $env:CHIRON_PROXY_BASE_URL = $defaultBaseUrl
}

$env:OPENAI_BASE_URL = $env:CHIRON_PROXY_BASE_URL
$env:OPENAI_API_BASE = $env:CHIRON_PROXY_BASE_URL
if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    $env:OPENAI_API_KEY = "ollama"
}

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    Write-Error "codex CLI was not found in PATH. Install Codex CLI first."
    exit 1
}

Write-Host "Starting Codex via ChironAI proxy..."
Write-Host "Base URL: $($env:OPENAI_BASE_URL)"
Write-Host "Tip: pass --model <your-build-id> to route through an LLM Proxy build."

& codex @CliArgs
exit $LASTEXITCODE
