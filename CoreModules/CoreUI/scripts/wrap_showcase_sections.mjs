import fs from 'fs';
import path from 'path';

const dir = path.resolve('src/components/showcase');
for (const file of fs.readdirSync(dir)) {
  if (!file.endsWith('Showcase.tsx')) continue;
  const fp = path.join(dir, file);
  let text = fs.readFileSync(fp, 'utf8');
  if (!text.includes('return (\n<ShowcaseSection')) continue;
  text = text.replace('return (\n<ShowcaseSection', 'return (\n    <>\n      <ShowcaseSection');
  if (!text.trimEnd().endsWith('</>\n  );\n}')) {
    text = text.replace(/\n\s*<\/>\s*\n\s*\);\s*\n\}/, '\n    </>\n  );\n}');
  }
  fs.writeFileSync(fp, text);
}
console.log('wrapped showcase sections');
