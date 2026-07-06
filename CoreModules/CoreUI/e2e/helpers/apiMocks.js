const DEFAULT_ONBOARDING_STATE = {
  version: 1,
  firstRunCompleted: false,
  tours: {
    builds: false,
    extensions: false,
    prompts: false,
    crawler: false,
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
    '/version': { version: '0.8.17', app_name: 'Chiron AI', app_stage: 'STABLE' },
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
      providers: [{ provider_id: 'ollama', title: 'Ollama' }],
      models: [{ provider_id: 'ollama', id: 'llama3', name: 'Llama 3' }],
    },
    '/provider-catalog': {
      providers: [{ provider_id: 'ollama', title: 'Ollama' }],
      models: [{ provider_id: 'ollama', id: 'llama3', name: 'Llama 3' }],
    },
    '/prompts': { prompts: [] },
    '/model-settings': {},
    '/pipeline-preview': { steps: [] },
    '/llm-proxy/builds': { builds, openai_models_urls: { main: 'http://127.0.0.1:5000/v1/models' } },
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

    if (request.method() === 'POST' || request.method() === 'PATCH' || request.method() === 'DELETE') {
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
