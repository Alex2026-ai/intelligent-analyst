import { test, expect } from '@playwright/test';

/**
 * Public Trust Feed — E2E verification.
 *
 * Tests the /trust-feed route renders correctly and does not
 * expose any private/tenant data in the DOM.
 */

test.describe('Public Trust Feed', () => {

  test('trust feed page loads', async ({ page }) => {
    await page.goto('/trust-feed');
    await expect(page.locator('text=Public Trust Feed')).toBeVisible({ timeout: 10000 });
  });

  test('unavailable feed shows graceful public demo fallback', async ({ page }) => {
    await page.goto('/trust-feed');
    const content = await page.textContent('body');
    expect(content).not.toContain('Unable to load trust feed');
    expect(content).toContain('Public demo feed');
    expect(content).toContain('Verified');
  });

  test('no tenant or private fields in DOM', async ({ page }) => {
    await page.goto('/trust-feed');
    await page.waitForTimeout(2000); // Wait for fetch to complete

    const html = await page.content();
    const forbidden = [
      'tenant_id', 'decision_id', 'source_resolution_id',
      'correlation_id', 'raw_response', 'raw_prompt',
      'chain_hash', 'node_hash', 'bucket_path', 'gcs_path',
    ];
    for (const field of forbidden) {
      expect(html).not.toContain(field);
    }
  });

  test('homepage trust feed section exists', async ({ page }) => {
    await page.goto('/');
    const section = page.locator('text=Public Trust Feed');
    // The section may or may not be visible depending on scroll
    // but it should exist in the DOM
    await expect(section.first()).toBeAttached({ timeout: 10000 });
  });

});
