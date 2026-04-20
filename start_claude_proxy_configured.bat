@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0start_claude_proxy_configured.ps1" -ProjectDir "%CD%" %*
