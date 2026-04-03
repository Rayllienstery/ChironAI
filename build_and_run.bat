@echo off

rem Build the application first
call scripts\build_app.bat

rem If the build succeeded, start the WebUI
rem start_webui.bat will exit with the same code as the server process
call start_webui.bat