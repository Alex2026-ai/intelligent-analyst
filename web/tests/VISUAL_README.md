# Visual Regression Testing

## Quick Start

```bash
cd web
npm install
npx playwright install chromium
npm run test:visual
```

## What Gets Tested (Automated)

The automated tests capture:

1. **Login Screen** - Unauthenticated landing page
2. **Login Button Hover** - Interactive state
3. **Shared View (Invalid Token)** - Error state for shared links

## Manual Visual Testing (Authenticated Screens)

Since Firebase auth requires Google Sign-In popup flow, authenticated screenshots
must be captured manually. Follow these steps:

### Prerequisites

1. Build the app: `npm run build`
2. Serve locally: `npm run preview` (or deploy to staging)
3. Open in Chrome with DevTools

### Screens to Capture

#### 1. Dashboard Landing (Post-Login)

1. Navigate to `http://localhost:4173`
2. Sign in with Google
3. Open DevTools → Device Toolbar → Responsive (1920x1080)
4. Screenshot: `Cmd+Shift+P` → "Capture full size screenshot"
5. Save as: `tests/visual.spec.ts-snapshots/04-dashboard-landing.png`

#### 2. Upload Screen (Idle State)

1. Click "Upload" tab in nav
2. Ensure no file is being processed
3. Screenshot full page
4. Save as: `tests/visual.spec.ts-snapshots/05-upload-idle.png`

#### 3. History Tab (Batch Table)

1. Click "History" tab
2. Ensure at least one batch is visible
3. Screenshot full page
4. Save as: `tests/visual.spec.ts-snapshots/06-history-table.png`

#### 4. Batch Detail Slide-Over

1. In History tab, click any batch row
2. Wait for slide-over panel to appear
3. Screenshot full page (including overlay)
4. Save as: `tests/visual.spec.ts-snapshots/07-batch-detail.png`

### Validation Checklist

When reviewing screenshots, verify:

- [ ] Token CSS variables are applied (check colors match tokens.css)
- [ ] Tables use dense styling with proper row height
- [ ] Monospace font for IDs (trace_id, batch_id)
- [ ] Status pills have correct semantic colors
- [ ] Flagged rows have left border indicator
- [ ] Nav header is compact (h-14)
- [ ] No marketing gradients or glow effects

### Updating Baselines

After styling changes:

```bash
npm run test:visual -- --update-snapshots
```

Or manually replace screenshots in `tests/visual.spec.ts-snapshots/`.

## CI Integration

For CI, implement one of:

1. **Firebase Test User**: Create a test account, store credentials in CI secrets
2. **Emulator**: Run Firebase Auth Emulator for automated sign-in
3. **Manual Gate**: Require manual screenshot approval before merge

Current implementation uses option 3 (manual gate).
