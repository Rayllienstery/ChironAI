import fs from 'fs';
import path from 'path';

const dir = path.resolve('src/components/showcase');
for (const file of fs.readdirSync(dir)) {
  if (!file.endsWith('Showcase.tsx')) continue;
  const fp = path.join(dir, file);
  let text = fs.readFileSync(fp, 'utf8');
  text = text.replace(/return \(\s*<>\s*<>\s*/m, 'return (\n    <>\n');
  text = text.replace(/\s*<>\s*$/m, '');
  text = text.replace(/\s*<\/>\s*<\/>\s*\);\s*}/m, '\n    </>\n  );\n}');
  fs.writeFileSync(fp, text);
}
console.log('fixed showcase fragments');
