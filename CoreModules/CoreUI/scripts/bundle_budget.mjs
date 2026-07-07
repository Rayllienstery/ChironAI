import fs from 'fs';
import path from 'path';

const distAssets = path.resolve('dist', 'assets');
const totalJsBudgetBytes = 1684096;

if (!fs.existsSync(distAssets)) {
  console.error('Bundle budget check failed: dist/assets does not exist. Run npm run build first.');
  process.exit(1);
}

const jsFiles = fs
  .readdirSync(distAssets)
  .filter((file) => file.endsWith('.js'))
  .map((file) => {
    const filePath = path.join(distAssets, file);
    return {
      file,
      bytes: fs.statSync(filePath).size,
    };
  });

if (!jsFiles.length) {
  console.error('Bundle budget check failed: no dist/assets/*.js files found.');
  process.exit(1);
}

const totalBytes = jsFiles.reduce((sum, item) => sum + item.bytes, 0);
const largest = [...jsFiles].sort((a, b) => b.bytes - a.bytes).slice(0, 5);

console.log(`CoreUI JS bundle total: ${totalBytes} bytes (budget ${totalJsBudgetBytes} bytes)`);
console.log('Largest JS assets:');
for (const item of largest) {
  console.log(`- ${item.file}: ${item.bytes} bytes`);
}

if (totalBytes > totalJsBudgetBytes) {
  console.error(
    `Bundle budget exceeded by ${totalBytes - totalJsBudgetBytes} bytes. ` +
      'Update the baseline only after reviewing intentional bundle growth.',
  );
  process.exit(1);
}
