/** Contextual feature tours (after first-run). */

import { t } from '../../services/i18n';

function resolveTourSteps(defs) {
  return defs.map((def) => ({
    ...def,
    title: t(def.titleKey),
    body: t(def.bodyKey),
  }));
}

const BUILDS_TOUR_STEP_DEFS = [
  {
    id: 'build-wizard',
    titleKey: 'onboarding.tour.builds.wizard.title',
    bodyKey: 'onboarding.tour.builds.wizard.body',
    target: '[data-tour="build-wizard"]',
  },
  {
    id: 'build-id',
    titleKey: 'onboarding.tour.builds.id.title',
    bodyKey: 'onboarding.tour.builds.id.body',
    target: '[data-tour="build-wizard-id"]',
  },
  {
    id: 'build-provider',
    titleKey: 'onboarding.tour.builds.provider.title',
    bodyKey: 'onboarding.tour.builds.provider.body',
    target: '[data-tour="build-wizard-provider"]',
  },
  {
    id: 'rag-collection',
    titleKey: 'onboarding.tour.builds.rag.title',
    bodyKey: 'onboarding.tour.builds.rag.body',
    target: '[data-tour="build-wizard-rag"]',
  },
  {
    id: 'save-build',
    titleKey: 'onboarding.tour.builds.save.title',
    bodyKey: 'onboarding.tour.builds.save.body',
    target: '[data-tour="build-wizard-save"]',
  },
];

export function createBuildsTourSteps({ goToBasicStep, goToRagStep } = {}) {
  const onEnterById = {
    'build-wizard': goToBasicStep,
    'build-id': goToBasicStep,
    'build-provider': goToBasicStep,
    'rag-collection': goToRagStep,
  };
  return resolveTourSteps(BUILDS_TOUR_STEP_DEFS).map((step) => ({
    ...step,
    onEnter: onEnterById[step.id],
  }));
}

const EXTENSIONS_TOUR_STEP_DEFS = [
  {
    id: 'extensions-intro',
    titleKey: 'onboarding.tour.extensions.intro.title',
    bodyKey: 'onboarding.tour.extensions.intro.body',
    target: '[data-tour="extensions-header"]',
  },
  {
    id: 'extensions-views',
    titleKey: 'onboarding.tour.extensions.views.title',
    bodyKey: 'onboarding.tour.extensions.views.body',
    target: '[data-tour="extensions-views"]',
  },
];

export function resolveExtensionsTourSteps() {
  return resolveTourSteps(EXTENSIONS_TOUR_STEP_DEFS);
}

const PROMPTS_TOUR_STEP_DEFS = [
  {
    id: 'prompts-new',
    titleKey: 'onboarding.tour.prompts.new.title',
    bodyKey: 'onboarding.tour.prompts.new.body',
    target: '[data-tour="template-new-btn"]',
  },
  {
    id: 'prompts-editor',
    titleKey: 'onboarding.tour.prompts.editor.title',
    bodyKey: 'onboarding.tour.prompts.editor.body',
    target: '[data-tour="template-editor-panel"]',
  },
];

export function resolvePromptsTourSteps() {
  return resolveTourSteps(PROMPTS_TOUR_STEP_DEFS);
}

const PROVIDERS_TOUR_STEP_DEFS = [
  {
    id: 'providers-intro',
    titleKey: 'onboarding.tour.providers.intro.title',
    bodyKey: 'onboarding.tour.providers.intro.body',
    target: '[data-tour="providers-header"]',
  },
  {
    id: 'providers-custom',
    titleKey: 'onboarding.tour.providers.custom.title',
    bodyKey: 'onboarding.tour.providers.custom.body',
    target: '[data-tour="providers-custom-list"]',
  },
  {
    id: 'providers-extensions',
    titleKey: 'onboarding.tour.providers.extensions.title',
    bodyKey: 'onboarding.tour.providers.extensions.body',
    target: '[data-tour="providers-extensions"]',
  },
];

export function resolveProvidersTourSteps() {
  return resolveTourSteps(PROVIDERS_TOUR_STEP_DEFS);
}

const CRAWLER_TOUR_STEP_DEFS = [
  {
    id: 'crawler-intro',
    titleKey: 'onboarding.tour.crawler.intro.title',
    bodyKey: 'onboarding.tour.crawler.intro.body',
    target: '[data-tour="crawler-header"]',
  },
  {
    id: 'crawler-section-tabs',
    titleKey: 'onboarding.tour.crawler.section_tabs.title',
    bodyKey: 'onboarding.tour.crawler.section_tabs.body',
    target: '[data-tour="crawler-section-tabs"]',
  },
  {
    id: 'crawler-sources-panel',
    titleKey: 'onboarding.tour.crawler.sources_panel.title',
    bodyKey: 'onboarding.tour.crawler.sources_panel.body',
    target: '[data-tour="crawler-sources"]',
  },
  {
    id: 'crawler-add-source',
    titleKey: 'onboarding.tour.crawler.add_source.title',
    bodyKey: 'onboarding.tour.crawler.add_source.body',
    target: '[data-tour="crawler-add-source"]',
  },
  {
    id: 'crawler-crawl-one',
    titleKey: 'onboarding.tour.crawler.crawl_one.title',
    bodyKey: 'onboarding.tour.crawler.crawl_one.body',
    target: '[data-tour="crawler-crawl-btn"]',
  },
  {
    id: 'crawler-crawl-batch',
    titleKey: 'onboarding.tour.crawler.crawl_batch.title',
    bodyKey: 'onboarding.tour.crawler.crawl_batch.body',
    target: '[data-tour="crawler-crawl-selected"]',
  },
  {
    id: 'crawler-source-detail',
    titleKey: 'onboarding.tour.crawler.source_detail.title',
    bodyKey: 'onboarding.tour.crawler.source_detail.body',
    target: '[data-tour="crawler-source-pages"]',
  },
  {
    id: 'crawler-create-collection',
    titleKey: 'onboarding.tour.crawler.create_collection.title',
    bodyKey: 'onboarding.tour.crawler.create_collection.body',
    target: '[data-tour="crawler-create-collection"]',
  },
  {
    id: 'crawler-collection-embed',
    titleKey: 'onboarding.tour.crawler.collection_embed.title',
    bodyKey: 'onboarding.tour.crawler.collection_embed.body',
    target: '[data-tour="crawler-collection-embed"]',
  },
  {
    id: 'crawler-collection-chunking',
    titleKey: 'onboarding.tour.crawler.collection_chunking.title',
    bodyKey: 'onboarding.tour.crawler.collection_chunking.body',
    target: '[data-tour="crawler-collection-chunking"]',
  },
  {
    id: 'crawler-md-pipeline-tab',
    titleKey: 'onboarding.tour.crawler.md_pipeline_tab.title',
    bodyKey: 'onboarding.tour.crawler.md_pipeline_tab.body',
    target: '[data-tour="crawler-md-pipeline-tab"]',
  },
  {
    id: 'crawler-pipeline-select',
    titleKey: 'onboarding.tour.crawler.pipeline_select.title',
    bodyKey: 'onboarding.tour.crawler.pipeline_select.body',
    target: '[data-tour="crawler-pipeline-select"]',
  },
  {
    id: 'crawler-pipeline-steps',
    titleKey: 'onboarding.tour.crawler.pipeline_steps.title',
    bodyKey: 'onboarding.tour.crawler.pipeline_steps.body',
    target: '[data-tour="crawler-pipeline-steps"]',
  },
  {
    id: 'crawler-next-rag',
    titleKey: 'onboarding.tour.crawler.next_rag.title',
    bodyKey: 'onboarding.tour.crawler.next_rag.body',
    target: '[data-tour="rag"]',
  },
];

export function createCrawlerTourSteps({
  setActiveSection,
  openCreateCollectionModal,
  closeModals,
  selectFirstSource,
  expandFirstMdStep,
} = {}) {
  const onEnterById = {
    'crawler-sources-panel': () => {
      closeModals?.();
      setActiveSection?.('crawler');
    },
    'crawler-crawl-one': () => {
      closeModals?.();
      setActiveSection?.('crawler');
      selectFirstSource?.();
    },
    'crawler-source-detail': () => {
      closeModals?.();
      setActiveSection?.('crawler');
      selectFirstSource?.();
    },
    'crawler-create-collection': () => {
      closeModals?.();
      setActiveSection?.('crawler');
    },
    'crawler-collection-embed': () => {
      setActiveSection?.('crawler');
      openCreateCollectionModal?.();
    },
    'crawler-collection-chunking': () => {
      setActiveSection?.('crawler');
      openCreateCollectionModal?.();
    },
    'crawler-md-pipeline-tab': () => {
      closeModals?.();
      setActiveSection?.('md-pipeline');
    },
    'crawler-pipeline-select': () => {
      closeModals?.();
      setActiveSection?.('md-pipeline');
    },
    'crawler-pipeline-steps': () => {
      closeModals?.();
      setActiveSection?.('md-pipeline');
      expandFirstMdStep?.();
    },
    'crawler-next-rag': () => closeModals?.(),
  };
  return resolveTourSteps(CRAWLER_TOUR_STEP_DEFS).map((step) => ({
    ...step,
    onEnter: onEnterById[step.id],
  }));
}

export function resolveCrawlerTourSteps() {
  return createCrawlerTourSteps();
}

/** @deprecated Use resolve*TourSteps() — kept for tests that assert step metadata. */
export const EXTENSIONS_TOUR_STEPS = EXTENSIONS_TOUR_STEP_DEFS;
/** @deprecated Use resolve*TourSteps() */
export const PROMPTS_TOUR_STEPS = PROMPTS_TOUR_STEP_DEFS;
/** @deprecated Use resolve*TourSteps() */
export const PROVIDERS_TOUR_STEPS = PROVIDERS_TOUR_STEP_DEFS;
/** @deprecated Use resolve*TourSteps() */
export const CRAWLER_TOUR_STEPS = CRAWLER_TOUR_STEP_DEFS;
