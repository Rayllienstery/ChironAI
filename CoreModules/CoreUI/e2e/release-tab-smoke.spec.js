import { expect, test } from '@playwright/test';
import { installApiMocks } from './helpers/apiMocks.js';

test.describe('release tab smoke', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page, { onboarding: 'completed' });
  });

  test('Dashboard renders the intro panel', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'ChironAI', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Modular RAG Platform' })).toBeVisible();
  });

  test('Settings renders theme controls and restart tour action', async ({ page }) => {
    await page.goto('/');
    await page.locator('[data-tour="settings"]').click();

    await expect(page.getByRole('heading', { level: 2, name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Restart tour' })).toBeVisible();
  });

  test('LLM Proxy Builds renders list actions', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'LLM Proxy Builds' }).click();

    await expect(page.getByRole('heading', { level: 2, name: 'LLM Proxy' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'New build' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
  });

  test('Logs tab renders log controls', async ({ page }) => {
    await page.goto('/');
    await page.locator('[data-tour="logs"]').click();

    await expect(page.getByRole('heading', { level: 2, name: 'Logs' })).toBeVisible();
    const logSources = page.getByRole('tablist', { name: 'Log source' });
    await expect(logSources).toBeVisible();
    await expect(logSources.getByRole('tab', { name: 'Logs', exact: true })).toBeVisible();
  });
});
