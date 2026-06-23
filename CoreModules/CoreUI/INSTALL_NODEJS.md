# Install Node.js and npm

React requires Node.js and npm.

## Option 1: Install Node.js (recommended)

1. Download the Node.js LTS version from the official site:
   https://nodejs.org/

2. Run the installer and follow the prompts
   - Make sure the option **"Add to PATH"** is enabled

3. Restart your terminal / PowerShell

4. Verify the installation:
   ```powershell
   node --version
   npm --version
   ```

5. After installation, run the build in the `webui_frontend` folder:
   ```powershell
   npm ci
   npm run build
   ```

## Option 2: Use an existing Node.js installation

If Node.js is already installed but not available in `PATH`:

1. Find the Node.js installation folder (usually `C:\Program Files\nodejs\`)

2. Add the folder to the system `PATH`:
   - Open **Environment Variables**
   - Find `PATH`
   - Add the Node.js folder (e.g. `C:\Program Files\nodejs\`)

3. Restart the terminal

## Alternative: Use without building

If you cannot install Node.js, you can use a simplified version without React.
Ask the developer to provide a plain JavaScript version.
