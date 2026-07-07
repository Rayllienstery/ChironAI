import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import zlib from 'zlib';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';

const gzip = promisify(zlib.gzip);
const brotliCompress = promisify(zlib.brotliCompress);

/**
 * Pre-compress all .js, .css, .svg, .json assets after build.
 * Flask serves these directly with Content-Encoding — zero runtime CPU overhead.
 */
function preCompressPlugin() {
  return {
    name: 'pre-compress',
    apply: 'build',
    async closeBundle() {
      const assetsDir = path.resolve('dist/assets');
      if (!fs.existsSync(assetsDir)) return;

      const EXTS = /\.(js|css|svg|json|woff2|woff|ttf)$/;
      const files = fs.readdirSync(assetsDir).filter(f => EXTS.test(f));

      let gzCount = 0;
      let brCount = 0;

      await Promise.all(files.map(async (file) => {
        const filePath = path.join(assetsDir, file);
        const content = fs.readFileSync(filePath);

        const [gz, br] = await Promise.all([
          gzip(content, { level: 9 }),
          brotliCompress(content, {
            params: { [zlib.constants.BROTLI_PARAM_QUALITY]: zlib.constants.BROTLI_MAX_QUALITY },
          }),
        ]);

        fs.writeFileSync(filePath + '.gz', gz);
        fs.writeFileSync(filePath + '.br', br);
        gzCount++;
        brCount++;
      }));

      console.log(`\x1b[32m✓\x1b[0m Pre-compressed ${gzCount} assets (gzip + brotli)`);
    },
  };
}

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || process.env.CHIRONAI_API_PROXY_TARGET || 'http://localhost:8080';

// CSP note: production Flask CSP is set in Core/api/http/security_headers.py.
// Vite dev/HMR needs eval; see docs/CSP_RISK_ACCEPTANCE.md (P2.9c).

export default defineConfig({
  plugins: [
    react(),
    preCompressPlugin(),
    visualizer({
      filename: 'dist/stats.html',
      open: false,
      gzipSize: true,
      brotliSize: true,
    }),
  ],
  server: {
    port: 3000,
    fs: {
      allow: ['..', '../..'],
    },
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1200,
  },
});

