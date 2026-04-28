#!/usr/bin/env node

/**
 * Marketing Asset Renderer
 *
 * Uses Playwright to capture real UI components as WebP/PNG assets.
 * Run with: npm run marketing:capture
 *
 * Prerequisites:
 *   npm install -D playwright sharp
 *   npx playwright install chromium
 */

import { chromium } from 'playwright';
import sharp from 'sharp';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../..');
const WEB_DIR = path.join(PROJECT_ROOT, 'web');
const OUTPUT_DIR = path.join(WEB_DIR, 'public', 'img');

const CAPTURES = [
  {
    name: 'dashboard-batch-overview',
    route: '/__capture/batch',
    viewport: { width: 1600, height: 900 },
  },
  {
    name: 'forensic-receipt',
    route: '/__capture/receipt',
    viewport: { width: 1600, height: 900 },
  },
  {
    name: 'public-verify',
    route: '/__capture/verify',
    viewport: { width: 1200, height: 900 },
  },
];

const DEV_PORT = 5199;
const DEV_URL = `http://localhost:${DEV_PORT}`;

async function startDevServer() {
  console.log('Starting Vite dev server...');

  const viteProcess = spawn('npm', ['run', 'dev', '--', '--port', String(DEV_PORT)], {
    cwd: WEB_DIR,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true,
  });

  // Wait for server to be ready
  return new Promise((resolve, reject) => {
    let output = '';

    const timeout = setTimeout(() => {
      viteProcess.kill();
      reject(new Error('Dev server startup timed out'));
    }, 30000);

    viteProcess.stdout.on('data', (data) => {
      output += data.toString();
      if (output.includes('Local:') || output.includes('ready in')) {
        clearTimeout(timeout);
        console.log('Dev server ready');
        resolve(viteProcess);
      }
    });

    viteProcess.stderr.on('data', (data) => {
      // Vite logs to stderr sometimes
      output += data.toString();
      if (output.includes('Local:') || output.includes('ready in')) {
        clearTimeout(timeout);
        console.log('Dev server ready');
        resolve(viteProcess);
      }
    });

    viteProcess.on('error', (err) => {
      clearTimeout(timeout);
      reject(err);
    });
  });
}

async function captureScreenshots(browser) {
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    deviceScaleFactor: 2, // Retina quality
    colorScheme: 'dark',
  });

  const page = await context.newPage();

  // Ensure output directory exists
  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  for (const capture of CAPTURES) {
    console.log(`Capturing: ${capture.name}`);

    // Set viewport for this capture
    await page.setViewportSize(capture.viewport);

    // Navigate to capture route
    await page.goto(`${DEV_URL}${capture.route}`, {
      waitUntil: 'networkidle',
    });

    // Wait for fonts to load
    await page.waitForTimeout(500);

    // Find the capture container
    const container = await page.$('#capture-container');
    if (!container) {
      console.error(`  Container not found for ${capture.name}`);
      continue;
    }

    // Capture PNG
    const pngPath = path.join(OUTPUT_DIR, `${capture.name}.png`);
    const pngBuffer = await container.screenshot({
      type: 'png',
      omitBackground: false,
    });
    await fs.writeFile(pngPath, pngBuffer);
    console.log(`  Saved: ${capture.name}.png`);

    // Convert to WebP
    const webpPath = path.join(OUTPUT_DIR, `${capture.name}.webp`);
    await sharp(pngBuffer)
      .webp({ quality: 90 })
      .toFile(webpPath);
    console.log(`  Saved: ${capture.name}.webp`);
  }

  await context.close();
}

async function main() {
  let viteProcess = null;
  let browser = null;

  try {
    // Start dev server
    viteProcess = await startDevServer();

    // Give it a moment to fully stabilize
    await new Promise((r) => setTimeout(r, 2000));

    // Launch browser
    console.log('Launching Playwright browser...');
    browser = await chromium.launch({
      headless: true,
    });

    // Capture all screenshots
    await captureScreenshots(browser);

    console.log('\n✓ All marketing assets generated successfully');
    console.log(`  Output: ${OUTPUT_DIR}`);

  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  } finally {
    // Cleanup
    if (browser) {
      await browser.close();
    }
    if (viteProcess) {
      viteProcess.kill();
    }
  }
}

main();
