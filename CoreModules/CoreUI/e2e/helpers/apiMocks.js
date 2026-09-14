const DEFAULT_ONBOARDING_STATE = {
  version: 1,
  firstRunCompleted: false,
  tours: {
    builds: false,
    extensions: false,
    prompts: false,
    crawler: false,
    providers: false,
    logs: false,
  },
};

const COMPLETED_ONBOARDING_STATE = {
  ...DEFAULT_ONBOARDING_STATE,
  firstRunCompleted: true,
  tours: {
    builds: true,
    extensions: true,
    prompts: true,
    crawler: true,
    providers: true,
    logs: false,
  },
};

function baseResponses(onboardingState, builds) {
  return {
    '/sessions': { id: 'e2e-session' },
    '/settings': {
      theme: 'system',
      onboarding_state: JSON.stringify(onboardingState),
    },
    '/version': { version: '0.8.19', app_name: 'Chiron AI', app_stage: 'STABLE' },
    '/dashboard-metrics': {
      cpu_percent: 0,
      memory_percent: 0,
      disk_percent: 0,
      ram: {
        system_used_gb: 16.7,
        system_total_gb: 32.0,
        app_gb: 1.2,
        app_host_bytes: 400000000,
        app_containers_bytes: 800000000,
      },
      cpu: { utilization_pct: 18 },
      services: [],
    },
    '/rag/status': {
      running: true,
      url: 'http://127.0.0.1:6333/dashboard',
      collections_count: 2,
      version: 'e2e',
    },
    '/rag/collections': {
      collections: [
        { name: 'docs', points_count: 10 },
        { name: 'api-docs', points_count: 5 },
      ],
    },
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
    '/providers/catalog': {
      providers: [
        { provider_id: 'ollama', title: 'Ollama' },
        { provider_id: 'my-gateway', title: 'My Gateway' },
      ],
      models: [
        { provider_id: 'ollama', id: 'llama3', name: 'Llama 3' },
        { provider_id: 'my-gateway', id: 'gpt-4o-mini', name: 'gpt-4o-mini' },
      ],
    },
    '/providers/custom': {
      providers: [
        {
          id: 'my-gateway',
          display_name: 'My Gateway',
          base_url: 'https://api.example.com/v1',
          enabled: true,
          api_key_configured: true,
        },
      ],
    },
    '/crawler/sources': {
      sources: [
        {
          id: 'docs-sample',
          url: 'https://example.com/docs',
          last_crawled: '2026-01-01T00:00:00Z',
          total_pages: 12,
          indexed_pages: 10,
          max_depth: 2,
          crawler: 'playwright',
          seed_urls: ['https://example.com/docs/start'],
        },
      ],
    },
    '/crawler/md-pipelines': { pipelines: ['default'] },
    '/crawler/md-pipelines/default': {
      name: 'default',
      steps: [
        {
          id: 'step-1',
          type: 'strip_meta_block',
          params: {},
        },
      ],
    },
    '/crawler/sources/docs-sample/pages': {
      pages: [
        {
          filename: 'intro.md',
          url: 'https://example.com/docs/intro',
          has_chunks: true,
          chunk_count: 4,
        },
      ],
    },
    '/provider-catalog': {
      providers: [{ provider_id: 'ollama', title: 'Ollama' }],
      models: [{ provider_id: 'ollama', id: 'llama3', name: 'Llama 3' }],
    },
    '/prompts': { prompts: [] },
    '/model-settings': {},
    '/pipeline-preview': { steps: [] },
    '/llm-proxy/builds': { builds, openai_models_urls: { main: 'http://127.0.0.1:5000/v1/models' } },
    '/llm-proxy/status': { running: true, base_url: 'http://127.0.0.1:8080' },
    '/logs': { logs: [], total: 0 },
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
    '/performance/snapshot': {
      captured_at_ms: 0,
      memory: {
        used_gb: 16.7,
        total_gb: 32.0,
        available_gb: 15.3,
        used_pct: 52,
        committed_gb: 18,
        committed_total_gb: 36,
      },
      app: {
        gb: 1.9,
        host_gb: 0.7,
        containers_gb: 1.2,
        bytes: 2040109465,
        host_bytes: 751619276,
        containers_bytes: 1288490189,
      },
      gpu: {
        name: 'NVIDIA GeForce RTX 4080',
        utilization_pct: 21,
        memory_used_mb: 2800,
        memory_total_mb: 16384,
        temperature_c: 46,
        driver_version: '32.0.16.1088',
      },
      processes: [
        { id: 'container:qdrant', kind: 'container', name: 'qdrant', rss: '900 MB', rss_bytes: 943718400, detail: 'Docker' },
        { id: 'proc:1', kind: 'process', name: 'python.exe', pid: 1, rss: '420 MB', rss_bytes: 440401920, detail: 'WebUI backend' },
      ],
    },
    '/host/phone-status': {
      host: 'awake',
      chiron: 'up',
      generating: false,
      kind: null,
      detail: null,
      gpu_pct: 3,
      active_traces: 0,
      status: 'Idle',
      message: 'PC awake, Chiron idle',
    },
    '/host/phone-scripts': {
      scripts: [
        {
          id: 'phone-host',
          file: 'phone-host.ps1',
          wrapper: 'phone-host.cmd',
          path: 'scripts/phone_host/phone-host.ps1',
          title: 'Phone host',
          description: 'iPhone Shortcut SSH entry: status, sleep, and router wake help.',
          enabled: true,
          exists: true,
          wrapper_exists: true,
        },
        {
          id: 'setup-openssh',
          file: 'setup-openssh.ps1',
          wrapper: null,
          path: 'scripts/phone_host/setup-openssh.ps1',
          title: 'OpenSSH setup',
          description: 'Installs OpenSSH Server and the dedicated iPhone key.',
          enabled: true,
          exists: true,
          wrapper_exists: false,
        },
      ],
    },
    '/help': {
      articles: [
        { slug: 'getting-started', title: 'Getting Started', tags: ['intro'] },
        { slug: 'builds', title: 'LLM Proxy Builds', tags: ['builds'] },
      ],
    },
  };
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ onboarding?: 'fresh' | 'completed' | object, mutableOnboarding?: boolean }} [options]
 */
export async function installApiMocks(page, options = {}) {
  const { onboarding = 'fresh', mutableOnboarding = false, builds = [] } = options;
  let onboardingState = onboarding === 'completed'
    ? structuredClone(COMPLETED_ONBOARDING_STATE)
    : onboarding === 'fresh'
      ? structuredClone(DEFAULT_ONBOARDING_STATE)
      : structuredClone(onboarding);
  let buildsStore = structuredClone(builds);

  await page.route('**/api/webui/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/webui', '');
    const responses = baseResponses(onboardingState, buildsStore);

    if (path === '/settings' && request.method() === 'POST') {
      let body = {};
      try {
        body = request.postDataJSON() ?? {};
      } catch {
        body = {};
      }
      if (body.onboarding_state) {
        try {
          onboardingState = JSON.parse(String(body.onboarding_state));
        } catch {
          /* keep previous state */
        }
      }
      await route.fulfill({
        json: {
          status: 'ok',
          theme: 'system',
          onboarding_state: JSON.stringify(onboardingState),
        },
      });
      return;
    }

    if (path === '/llm-proxy/builds' && request.method() === 'PUT') {
      let body = {};
      try {
        body = request.postDataJSON() ?? {};
      } catch {
        body = {};
      }
      buildsStore = Array.isArray(body.builds) ? body.builds : [];
      await route.fulfill({ json: { builds: buildsStore, openai_models_urls: responses['/llm-proxy/builds'].openai_models_urls } });
      return;
    }

    if (path.match(/^\/providers\/custom\/[^/]+\/test$/) && request.method() === 'POST') {
      await route.fulfill({
        json: {
          ok: true,
          status: 'ok',
          message: '',
          model_count: 1,
          models: [{ id: 'gpt-4o-mini', label: 'gpt-4o-mini' }],
        },
      });
      return;
    }

    if (path.startsWith('/providers/custom/') && request.method() === 'DELETE') {
      await route.fulfill({ json: { ok: true } });
      return;
    }

    if (request.method() === 'POST' || request.method() === 'PATCH' || request.method() === 'PUT') {
      await route.fulfill({ json: { ok: true } });
      return;
    }

    if (path.startsWith('/help/')) {
      const slug = path.replace('/help/', '').split('/')[0] || 'getting-started';
      await route.fulfill({
        json: {
          slug,
          title: slug === 'builds' ? 'LLM Proxy Builds' : 'Getting Started',
          content:
            slug === 'builds'
              ? '# LLM Proxy Builds\n\nE2E builds help body.'
              : '# Getting Started\n\nE2E help body.',
          tags: slug === 'builds' ? ['builds'] : ['intro'],
        },
      });
      return;
    }

    if (path === '/llm-proxy/builds') {
      await route.fulfill({ json: responses['/llm-proxy/builds'] });
      return;
    }

    if (path === '/logs') {
      await route.fulfill({ json: responses['/logs'] });
      return;
    }

    if (path === '/crawler/sources') {
      await route.fulfill({ json: responses['/crawler/sources'] });
      return;
    }

    if (path === '/crawler/md-pipelines') {
      await route.fulfill({ json: responses['/crawler/md-pipelines'] });
      return;
    }

    const mdPipelineMatch = path.match(/^\/crawler\/md-pipelines\/([^/]+)$/);
    if (mdPipelineMatch) {
      const name = decodeURIComponent(mdPipelineMatch[1]);
      const pipeline = responses['/crawler/md-pipelines/default'];
      await route.fulfill({
        json: name === 'default' ? pipeline : { name, steps: [] },
      });
      return;
    }

    const sourcePagesMatch = path.match(/^\/crawler\/sources\/([^/]+)\/pages$/);
    if (sourcePagesMatch) {
      await route.fulfill({ json: responses['/crawler/sources/docs-sample/pages'] });
      return;
    }

    await route.fulfill({ json: responses[path] ?? {} });
  });

  if (mutableOnboarding) {
    return {
      getOnboardingState: () => structuredClone(onboardingState),
    };
  }

  return null;
}

export async function clearOnboardingStorage(page) {
  await page.addInitScript(() => {
    window.localStorage.removeItem('chironai_onboarding_v1');
  });
}
