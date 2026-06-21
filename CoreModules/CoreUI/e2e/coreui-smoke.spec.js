import { expect, test } from '@playwright/test';

async function installApiMocks(page) {
  await page.route('**/api/webui/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/webui', '');

    const responses = {
      '/sessions': { id: 'e2e-session' },
      '/settings': { theme: 'system' },
      '/dashboard-metrics': {
        cpu_percent: 0,
        memory_percent: 0,
        disk_percent: 0,
        services: [],
      },
      '/rag/status': {
        running: true,
        url: 'http://127.0.0.1:6333/dashboard',
        collections_count: 2,
        version: 'e2e',
      },
      '/rag/collections': { collections: [{ name: 'docs' }] },
      '/rag/keyword-collections': { collections: [] },
      '/rag/trigger-settings': { threshold: 5 },
      '/rag/framework-settings': { framework_ttl_seconds: 300 },
      '/rag/model-settings': {
        rag_embed_provider_id: '',
        rag_embed_model: '',
        rag_rerank_provider_id: '',
        rerank_model: '',
        hybrid_sparse_enabled: false,
        rerank_for_rag: false,
        advanced_retrieval: {},
      },
      '/provider-catalog': { providers: [], models: [] },
      '/extensions/registry': {
        extensions: [
          {
            id: 'ollama-provider',
            title: 'Ollama Provider',
            version: '1.0.0',
            description: 'Local model provider',
            status: 'available',
          },
        ],
      },
      '/extensions/installed': {
        extensions: [
          {
            id: 'ollama-provider',
            title: 'Ollama Provider',
            version: '1.0.0',
            enabled: true,
            status: 'installed',
          },
        ],
      },
      '/extensions/providers': {
        providers: [
          {
            provider_id: 'ollama-provider',
            title: 'Ollama Provider',
            status: 'loaded',
          },
        ],
      },
      '/extensions/ui': { extensions: [], failed: [] },
      '/extensions/tabs': { tabs: [] },
      '/notifications': { notifications: [] },
      '/performance/startup': { modules: [] },
    };

    if (request.method() === 'POST' || request.method() === 'PATCH' || request.method() === 'DELETE') {
      await route.fulfill({ json: { ok: true } });
      return;
    }

    await route.fulfill({ json: responses[path] ?? {} });
  });
}

test.beforeEach(async ({ page }) => {
  await installApiMocks(page);
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
