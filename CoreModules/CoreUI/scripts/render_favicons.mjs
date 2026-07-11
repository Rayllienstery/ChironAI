/**
 * Rasterize favicon SVG sources to PNG (anti-aliased via resvg).
 * Run: node scripts/render_favicons.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { Resvg } from '@resvg/resvg-js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(__dirname, '../public');

function renderSvgToPng(svgPath, outPath, size) {
  const svg = fs.readFileSync(svgPath);
  const resvg = new Resvg(svg, {
    fitTo: { mode: 'width', value: size },
  });
  fs.writeFileSync(outPath, resvg.render().asPng());
  console.log(`wrote ${path.basename(outPath)} (${size}x${size})`);
}

const fullSvg = path.join(publicDir, 'favicon-full.svg');
const tinySvg = path.join(publicDir, 'favicon-16.svg');

renderSvgToPng(tinySvg, path.join(publicDir, 'favicon-16.png'), 16);

for (const size of [32, 180, 512]) {
  renderSvgToPng(fullSvg, path.join(publicDir, `favicon-${size}.png`), size);
}

fs.copyFileSync(path.join(publicDir, 'favicon-180.png'), path.join(publicDir, 'apple-touch-icon.png'));
console.log('wrote apple-touch-icon.png');
