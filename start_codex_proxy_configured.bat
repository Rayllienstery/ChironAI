@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0start_codex_proxy_configured.ps1" -ProjectDir "%CD%" %*
