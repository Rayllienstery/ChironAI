/** Contextual feature tours (after first-run). */

export function createBuildsTourSteps({ goToBasicStep, goToRagStep } = {}) {
  return [
    {
      id: 'build-wizard',
      title: 'Create or edit a build',
      body: 'This wizard defines a stable API model id plus provider, RAG collection, privacy, and generation parameters.',
      target: '[data-tour="build-wizard"]',
      onEnter: goToBasicStep,
    },
    {
      id: 'build-id',
      title: 'Build id',
      body: 'The id becomes the OpenAI `model` string clients send. Pick something short, unique, and lowercase.',
      target: '[data-tour="build-wizard-id"]',
      onEnter: goToBasicStep,
    },
    {
      id: 'rag-collection',
      title: 'Per-build RAG collection',
      body: 'Override the global Qdrant collection for this build only. Leave empty to inherit the server default.',
      target: '[data-tour="build-wizard-rag"]',
      onEnter: goToRagStep,
    },
    {
      id: 'save-build',
      title: 'Save the build',
      body: 'When finished, save here. The build appears in GET /v1/models for external clients.',
      target: '[data-tour="build-wizard-save"]',
    },
  ];
}

export const EXTENSIONS_TOUR_STEPS = [
  {
    id: 'extensions-intro',
    title: 'Extensions',
    body: 'Extensions add LLM providers, Docker services, and extra CoreUI tabs. Install from Registry or enable bundled ones.',
    target: '[data-tour="extensions-header"]',
  },
  {
    id: 'extensions-views',
    title: 'Installed vs Registry',
    body: 'Use Installed to manage running extensions. Open Registry to browse available packages and install new capabilities.',
    target: '[data-tour="extensions-views"]',
  },
];

export const PROMPTS_TOUR_STEPS = [
  {
    id: 'prompts-new',
    title: 'Prompt templates',
    body: 'Templates become system prompts for builds. Create reusable instructions for coding, review, or support workflows.',
    target: '[data-tour="template-new-btn"]',
  },
  {
    id: 'prompts-editor',
    title: 'Structured editor',
    body: 'Edit title, description, and body sections—or switch to raw mode. Use the in-editor assistant for linting and structure hints.',
    target: '[data-tour="template-editor-panel"]',
  },
];

export const CRAWLER_TOUR_STEPS = [
  {
    id: 'crawler-intro',
    title: 'Indexer / Crawler',
    body: 'Ingest documentation and source into markdown stores, then embed chunks into Qdrant collections for RAG.',
    target: '[data-tour="crawler-header"]',
  },
  {
    id: 'crawler-sources',
    title: 'Sources & pipelines',
    body: 'Configure crawl sources, run indexing jobs, and monitor progress before testing retrieval in RAG or Model Tester.',
    target: '[data-tour="crawler-sources"]',
  },
];
