import { expect, test } from '@playwright/test';
import { clearOnboardingStorage, installApiMocks } from './helpers/apiMocks.js';

test.describe('crawler contextual tour', () => {
  test('shows crawler tour on first visit and can be skipped', async ({ page }) => {
    await clearOnboardingStorage(page);
    await page.addInitScript(() => {
      window.localStorage.setItem(
        'chironai_onboarding_v1',
        JSON.stringify({
          version: 1,
          firstRunCompleted: true,
          tours: {
            builds: true,
            extensions: true,
            prompts: true,
            crawler: false,
            providers: true,
            logs: false,
          },
        }),
      );
    });
    await installApiMocks(page, {
      onboarding: {
        version: 1,
        firstRunCompleted: true,
        tours: {
          builds: true,
          extensions: true,
          prompts: true,
          crawler: false,
          providers: true,
          logs: false,
        },
      },
    });
    await page.goto('/');

    await page.locator('[data-tour="crawler"]').click();

    const tourDialog = page.getByRole('dialog', { name: 'Indexer / Crawler' });
    await expect(tourDialog).toBeVisible({ timeout: 15_000 });
    await expect(tourDialog.getByText(/Step 1 of 14/i)).toBeVisible();
    await expect(page.getByText('docs-sample')).toBeVisible();

    await page.getByRole('button', { name: 'Skip tour' }).click();
    await expect(tourDialog).toBeHidden();

    const stored = await page.evaluate(() => window.localStorage.getItem('chironai_onboarding_v1'));
    expect(JSON.parse(stored || '{}').tours.crawler).toBe(true);
  });
});
