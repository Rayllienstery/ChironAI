# Installation and build instructions

## Option 1: Use `.bat` files (recommended)

Run in PowerShell or CMD:

```cmd
.\install_dependencies.bat
.\build_app.bat
```

## Option 2: Use `npm.cmd` directly

In PowerShell:

```powershell
npm.cmd ci
npm.cmd run build
```

## Option 3: Change the PowerShell execution policy (current session only)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
npm ci
npm run build
```

## Option 4: Use CMD instead of PowerShell

Open `cmd.exe` and run:

```cmd
cd C:\Users\Raylee\AI\webui_frontend
npm ci
npm run build
```

## After a successful build

Start the Flask server:

```powershell
cd C:\Users\Raylee\AI
python -m webui_backend.rag_proxy
```

WebUI will be available at the configured server port, for example: http://localhost:8080/webui
