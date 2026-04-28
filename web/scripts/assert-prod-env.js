import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distJs = join(__dirname, '..', 'dist', 'assets');

// Read the built JS bundle and verify PROD is baked in, not TEST
import { readdirSync } from 'fs';
const jsFiles = readdirSync(distJs).filter(f => f.endsWith('.js'));
if (jsFiles.length === 0) {
  console.error("❌ No JS files in dist/assets — did you build first?");
  process.exit(1);
}

const bundle = jsFiles
  .map((file) => readFileSync(join(distJs, file), 'utf-8'))
  .join('\n');

if (bundle.includes('backend-test')) {
  console.error("❌ Refusing to deploy: Bundle references TEST backend (backend-test)");
  process.exit(1);
}

if (!bundle.includes('api-hardened')) {
  console.error("❌ Refusing to deploy: Bundle does not reference PROD backend (api-hardened)");
  process.exit(1);
}

console.log(`✅ PROD environment verified across ${jsFiles.length} JS chunks — bundle points to api-hardened, no TEST references`);
