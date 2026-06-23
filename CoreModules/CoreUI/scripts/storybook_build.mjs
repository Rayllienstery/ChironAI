import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import process from 'process';

const root = process.cwd();
const localHome = path.join(root, '.storybook-home');
const localCache = path.join(root, '.storybook-cache');

fs.mkdirSync(localHome, { recursive: true });
fs.mkdirSync(localCache, { recursive: true });

const storybookCli = path.join(root, 'node_modules', 'storybook', 'bin', 'index.cjs');
const result = spawnSync(process.execPath, [storybookCli, 'build'], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    CI: '1',
    HOME: localHome,
    USERPROFILE: localHome,
    STORYBOOK_DISABLE_TELEMETRY: '1',
    STORYBOOK_CACHE_DIR: localCache,
  },
});

if (result.error) {
  console.error(result.error);
}

process.exit(result.status ?? 1);
