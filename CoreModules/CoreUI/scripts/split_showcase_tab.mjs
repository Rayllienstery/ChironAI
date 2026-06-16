import fs from 'fs';
import path from 'path';

const root = path.resolve('src/components');
const srcPath = path.join(root, 'CoreUIShowcaseTab.jsx');
const outDir = path.join(root, 'showcase');
const lines = fs.readFileSync(srcPath, 'utf8').split(/\r?\n/);

const ranges = {
  ColorsShowcase: [118, 236],
  ButtonsShowcase: [238, 289],
  CardsShowcase: [291, 489],
  ComponentsShowcase: [491, 577],
  LayoutShowcase: [579, 863],
  DataShowcase: [865, 1192],
  IconsShowcase: [1194, 1212],
  NotificationsShowcase: [1214, lines.length - 3],
};

const sharedImports = `import { CodePill, ShowcaseItem, ShowcaseSection, TokenSwatch, FontCard, sourceRoot } from './CoreUIShowcasePrimitives';
import Card from '../Card';
import CoreUIButton from '../CoreUIButton';
import CoreUIBadge from '../CoreUIBadge';
import CoreUIDockerCard from '../CoreUIDockerCard';
import CoreUINotificationActionButton from '../CoreUINotificationActionButton';
import CoreUISubtabs from '../CoreUISubtabs';
import CoreUISlider from '../CoreUISlider';
import EmptyState from '../EmptyState';
import ExtensionRuntimeLoadingView, { buildExtensionRuntimeLoadingSteps } from '../ExtensionRuntimeLoadingView';
import StandByScreen from '../StandByScreen';
import CoreUIPipelinePreview from '../CoreUIPipelinePreview';
import ExtensionRuntimeModelCard from '../extensionRuntimeTab/ExtensionRuntimeModelCard';
`;

fs.mkdirSync(outDir, { recursive: true });

for (const [name, [start, end]] of Object.entries(ranges)) {
  let chunk = lines.slice(start - 1, end).join('\n');
  chunk = chunk.replace(/^\s*\{subtab === "[^"]+" && \(\s*/, '').replace(/\)\}\s*$/, '');
  const content = `${sharedImports}

export default function ${name}() {
  return (
    <>
${chunk}
    </>
  );
}
`;
  fs.writeFileSync(path.join(outDir, `${name}.tsx`), content);
}

console.log('Wrote', Object.keys(ranges).length, 'showcase files');
