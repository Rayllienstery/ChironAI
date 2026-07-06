import { expect, test } from '@playwright/test';
import { clearOnboardingStorage, installApiMocks } from './helpers/apiMocks.js';

test.describe('providers contextual tour', () => {
  test('shows providers tour on first visit and can be skipped', async ({ page }) => {
    await clearOnboardingStorage(page);
    await installApiMocks(page, {
      onboarding: {
        version: 1,
        firstRunCompleted: true,
        tours: {
          builds: true,
          extensions: true,
          prompts: true,
          crawler: true,
          providers: false,
          logs: false,
        },
      },
    });
    await page.goto('/');

    await page.locator('[data-tour="providers"]').click();

    const tourDialog = page.getByRole('dialog', { name: 'Upstream providers' });
    await expect(tourDialog).toBeVisible({ timeout: 15_000 });
    await expect(tourDialog.getByText(/Step 1 of 3/i)).toBeVisible();
    await expect(page.getByText('My Gateway')).toBeVisible();

    await page.getByRole('button', { name: 'Skip tour' }).click();
    await expect(tourDialog).toBeHidden();

    const stored = await page.evaluate(() => window.localStorage.getItem('chironai_onboarding_v1'));
    expect(JSON.parse(stored || '{}').tours.providers).toBe(true);
  });
});
