@echo off
@echo Python version before installation:
python --version
@echo.

@echo Installing Python dependencies (without problematic packages)...
@echo.

REM Install core dependencies first
@echo Installing Flask and core dependencies...
for %%p in (flask requests qdrant-client langchain-text-splitters) do (
  python -m pip show %%p >nul 2>&1
  if errorlevel 1 (
    python -m pip install %%p
  )
)
@echo Python version after core dependencies:
python --version
@echo.

REM Try to install lxml with pre-built wheel
@echo.
@echo Lxml installation check...
for %%p in (lxml) do (
    python -m pip show %%p >nul 2>&1
    if errorlevel 1 (
        python -m pip install --only-binary=%%p %%p
        echo Installed %%p
    ) else (
        for /f "tokens=2 delims=: " %%v in ('python -m pip show %%p ^| findstr "Version:"') do (
            echo %%p version: %%v
        )
    )
)
@echo python version after lxml:
python --version
@echo.

REM Install optional dependencies (html2text, playwright)
@echo.
@echo Optional dependencies check...
for %%p in (html2text playwright) do (
    python -m pip show %%p >nul 2>&1
    if errorlevel 1 (
        python -m pip install %%p
        echo Installed %%p
    ) else (
        for /f "tokens=2 delims=: " %%v in ('python -m pip show %%p ^| findstr "Version:"') do (
            echo %%p version: %%v
        )
    )
)
@echo python version after optional deps:
python --version
@echo.

@echo.
@echo ========================================
@echo Core dependencies installed!
@echo WebUI should be functional now.
@echo ========================================
@echo.
@pause
