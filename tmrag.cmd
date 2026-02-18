@echo off
REM TMRagFetcher CLI — open Command Prompt, show help, then leave it open so you can type commands.
cd /d "%~dp0"
python tmrag.py --help
echo.
echo You can now run: python tmrag.py start ^| crawl ^| index ^| ...
cmd /k
