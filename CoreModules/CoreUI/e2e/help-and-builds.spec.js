import { expect, test } from '@playwright/test';
import { clearOnboardingStorage, installApiMocks } from './helpers/apiMocks.js';

const FIRST_RUN_DONE_BUILDS_TOUR_PENDING = {
  version: 1,
  firstRunCompleted: true,
  tours: {
    builds: false,
    extensions: true,
    prompts: true,
    crawler: true,
    logs: false,
  },
};

test.describe('help flows', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page, { onboarding: 'completed' });
  });

  test('?help=builds opens the Help tab on the requested article', async ({ page }) => {
    await page.goto('/?help=builds');

    await expect(page.getByRole('heading', { level: 1, name: 'Help' })).toBeVisible();
    await expect(page.getByText(/E2E builds help body/i)).toBeVisible();
    await expect(page).not.toHaveURL(/\?help=/);
  });

  test('InfoButton on builds list opens the contextual help drawer', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'LLM Proxy Builds' }).click();

    await page.getByRole('button', { name: 'Help: LLM Proxy Builds' }).click();

    const panel = page.getByRole('dialog', { name: /LLM Proxy Builds/i });
    await expect(panel).toBeVisible();
    await expect(panel.getByText(/E2E builds help body/i)).toBeVisible();
  });
});

test.describe('builds contextual tour', () => {
  test('shows the builds wizard tour when creating a new build', async ({ page }) => {
    await clearOnboardingStorage(page);
    await installApiMocks(page, { onboarding: FIRST_RUN_DONE_BUILDS_TOUR_PENDING });

    await page.goto('/');
    await page.getByRole('button', { name: 'LLM Proxy Builds' }).click();
    await page.getByRole('button', { name: 'New build' }).click();

    await expect(page.getByText('Create new build')).toBeVisible();
    await expect(page.getByRole('dialog', { name: 'Create or edit a build' })).toBeVisible({
      timeout: 15_000,
    });
  });
});
