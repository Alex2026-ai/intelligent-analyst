import { existsSync, readFileSync, readdirSync, statSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distDir = join(__dirname, '..', 'dist');
const assetsDir = join(distDir, 'assets');

const failures = [];

function fail(message) {
  failures.push(message);
}

function assertFile(path, label) {
  if (!existsSync(path)) {
    fail(`${label} is missing: ${path}`);
    return false;
  }
  if (statSync(path).size === 0) {
    fail(`${label} is empty: ${path}`);
    return false;
  }
  return true;
}

assertFile(join(distDir, 'index.html'), 'SPA entry');
assertFile(join(distDir, 'favicon.svg'), 'favicon');
assertFile(join(distDir, 'og-image.png'), 'Open Graph image');
assertFile(join(distDir, 'apple-touch-icon.png'), 'Apple touch icon');

let bundle = '';
let previewBundle = '';
if (!existsSync(assetsDir)) {
  fail(`assets directory is missing: ${assetsDir}`);
} else {
  const jsFiles = readdirSync(assetsDir).filter((file) => file.endsWith('.js'));
  if (jsFiles.length === 0) {
    fail('No JS chunks found in dist/assets');
  }
  bundle = jsFiles
    .map((file) => readFileSync(join(assetsDir, file), 'utf-8'))
    .join('\n');
  previewBundle = jsFiles
    .map((file) => readFileSync(join(assetsDir, file), 'utf-8'))
    .find((content) => content.includes('Interactive Public Demo')) || '';
  if (!previewBundle) {
    fail('Could not locate the public preview JS chunk');
  }
}

const requiredText = [
  'Interactive Public Demo',
  'Run Sample Upload',
  'Download Sample Evidence Pack',
  'No backend calls',
  'Sample evidence pack downloaded',
  'Demo Configuration',
];

for (const text of requiredText) {
  if (!previewBundle.includes(text)) {
    fail(`Public demo bundle is missing expected text: "${text}"`);
  }
}

const forbiddenPreviewText = [
  'Preview Mode — Visual demo only',
  'Visual demo only',
  'Drop your file here',
  'Admin configuration panel',
];

for (const text of forbiddenPreviewText) {
  if (previewBundle.includes(text)) {
    fail(`Public preview bundle still contains forbidden text: "${text}"`);
  }
}

const forbiddenGlobalText = [
  '[debug] Test auth handler',
  'demo@intelligentanalyst',
  'VITE_DASHBOARD_URL',
  ['intelligent-analyst-enterprise', 'web.app/app'].join('.'),
];

for (const text of forbiddenGlobalText) {
  if (bundle.includes(text)) {
    fail(`Built assets still contain forbidden text: "${text}"`);
  }
}

if (failures.length > 0) {
  console.error('❌ Public build smoke failed');
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log('✅ Public build smoke passed — assets, demo copy, and debug-string checks are clean');
