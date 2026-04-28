import { copyFileSync, existsSync } from 'fs';
import { join } from 'path';

const distDir = join(process.cwd(), 'dist');
const indexPath = join(distDir, 'index.html');
const fallbackPath = join(distDir, '404.html');

if (!existsSync(indexPath)) {
  console.error(`Missing built index file: ${indexPath}`);
  process.exit(1);
}

copyFileSync(indexPath, fallbackPath);
console.log('Prepared GitHub Pages SPA fallback: dist/404.html');
