import { test, expect } from '@playwright/test';

/**
 * Visual Regression Tests for Intelligent Analyst Dashboard
 *
 * These tests capture screenshots for visual comparison.
 * Run: npm run test:visual
 *
 * Note: These tests run against the login screen (unauthenticated state).
 * For authenticated screenshots, see VISUAL_README.md for manual steps.
 */

test.describe('Visual Regression - Unauthenticated', () => {

  test('login screen', async ({ page }) => {
    await page.goto('/');

    // Wait for the sign-in page to load
    await page.waitForSelector('text=Sign in', { timeout: 10000 });

    // Take screenshot of login screen
    await expect(page).toHaveScreenshot('01-login-screen.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('login screen - button hover state', async ({ page }) => {
    await page.goto('/');

    await page.waitForSelector('text=Continue with Google', { timeout: 10000 });

    // Hover over the sign-in button
    await page.hover('text=Continue with Google');

    await expect(page).toHaveScreenshot('02-login-button-hover.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

});

test.describe('Visual Regression - Shared View', () => {

  test('shared batch view - invalid token', async ({ page }) => {
    // Navigate to a share link with invalid token
    await page.goto('/s/invalid-token-test');

    // Wait for error state to render
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('03-shared-view-invalid.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

});

/**
 * Authenticated visual tests would require:
 * 1. A test Firebase user with credentials stored in env
 * 2. Programmatic login via Firebase Admin SDK
 * 3. Or: Manual screenshot capture documented in VISUAL_README.md
 *
 * For now, the unauthenticated screenshots validate:
 * - Token layer CSS is loading correctly
 * - Login UI styling is consistent
 * - Shared view error states render correctly
 */
