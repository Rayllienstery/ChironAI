# Quick Node.js check

## Method 1: Run the `.bat` file

```cmd
check_nodejs.bat
```

## Method 2: Run commands directly

In PowerShell:

```powershell
# Check Node.js
node --version

# Check npm
npm --version
```

If the commands work, Node.js is installed and ready to use.

## Method 3: Bypass execution policy for `.ps1`

If you need to run the `.ps1` script, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\check_nodejs.ps1
```

## If Node.js is not installed

1. Download from https://nodejs.org/ (LTS version)
2. Install with the option **"Add to PATH"**
3. Restart your terminal
4. Check again: `node --version`

