import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { installApiMocks } from './helpers/apiMocks.js';

const TAB_CHECKS = [
  { nav: 'Dashboard', heading: { name: 'ChironAI', exact: true } },
  { nav: 'RAG / Qdrant', heading: { name: 'RAG / Qdrant', level: 2 } },
  { nav: 'Extensions', heading: { name: 'Extensions', exact: true, level: 2 } },
  { nav: 'Crawler / Indexer', heading: { name: 'Crawler / Indexer', level: 2 } },
];

test.beforeEach(async ({ page }) => {
  await installApiMocks(page, { onboarding: 'completed' });
});

for (const tab of TAB_CHECKS) {
  test(`${tab.nav} tab passes axe smoke`, async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: tab.nav }).click();
    await expect(page.getByRole('heading', tab.heading)).toBeVisible();

    const results = await new AxeBuilder({ page })
      .include('.tab-view')
      .disableRules(['color-contrast'])
      .analyze();

    const serious = results.violations.filter((violation) =>
      ['serious', 'critical'].includes(violation.impact),
    );
    expect(serious).toEqual([]);
  });
}
