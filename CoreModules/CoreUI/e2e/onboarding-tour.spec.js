import { expect, test } from '@playwright/test';
import { clearOnboardingStorage, installApiMocks } from './helpers/apiMocks.js';

test.describe('onboarding tour', () => {
  test('first-run tour can be skipped and persists completion', async ({ page }) => {
    await clearOnboardingStorage(page);
    await installApiMocks(page, { onboarding: 'fresh' });
    await page.goto('/');

    const tourDialog = page.getByRole('dialog', { name: 'Welcome to ChironAI' });
    await expect(tourDialog).toBeVisible();
    await expect(tourDialog.getByText(/Step 1 of 5/i)).toBeVisible();

    await page.getByRole('button', { name: 'Skip tour' }).click();
    await expect(tourDialog).toBeHidden();

    const stored = await page.evaluate(() => window.localStorage.getItem('chironai_onboarding_v1'));
    expect(JSON.parse(stored || '{}').firstRunCompleted).toBe(true);
  });

  test('settings restart tour shows the walkthrough again after reload', async ({ page }) => {
    await clearOnboardingStorage(page);
    await installApiMocks(page, { onboarding: 'completed', mutableOnboarding: true });
    await page.goto('/');

    await expect(page.getByRole('dialog', { name: 'Welcome to ChironAI' })).toBeHidden();

    await page.locator('[data-tour="settings"]').click();
    await expect(page.getByRole('button', { name: 'Restart tour' })).toBeVisible();

    await page.getByRole('button', { name: 'Restart tour' }).click();

    await expect(page.getByRole('dialog', { name: 'Welcome to ChironAI' })).toBeVisible({
      timeout: 15_000,
    });
  });
});
