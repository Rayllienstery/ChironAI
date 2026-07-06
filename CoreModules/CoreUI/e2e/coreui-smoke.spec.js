import { expect, test } from '@playwright/test';
import { installApiMocks } from './helpers/apiMocks.js';

test.beforeEach(async ({ page }) => {
  await installApiMocks(page, { onboarding: 'completed' });
});

test('RAG request flow renders pipeline guidance', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'RAG / Qdrant' }).click();

  await expect(page.getByRole('heading', { name: /RAG \/ Qdrant/i })).toBeVisible();
  await expect(page.getByText('RAG pipeline map')).toBeVisible();
  await expect(page.getByText('http://127.0.0.1:6333/dashboard')).toBeVisible();
});

test('extension management smoke renders installed and registry surfaces', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /^Extensions$/ }).click();

  await expect(page.getByRole('heading', { name: /^Extensions$/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Installed' })).toBeVisible();
  await expect(page.getByText('Ollama Provider')).toBeVisible();
});
