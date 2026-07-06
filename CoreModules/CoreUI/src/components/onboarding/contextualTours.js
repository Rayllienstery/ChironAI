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
    id: 'crawler-sources',
    titleKey: 'onboarding.tour.crawler.sources.title',
    bodyKey: 'onboarding.tour.crawler.sources.body',
    target: '[data-tour="crawler-sources"]',
  },
];

export function resolveCrawlerTourSteps() {
  return resolveTourSteps(CRAWLER_TOUR_STEP_DEFS);
}

/** @deprecated Use resolve*TourSteps() — kept for tests that assert step metadata. */
export const EXTENSIONS_TOUR_STEPS = EXTENSIONS_TOUR_STEP_DEFS;
/** @deprecated Use resolve*TourSteps() */
export const PROMPTS_TOUR_STEPS = PROMPTS_TOUR_STEP_DEFS;
/** @deprecated Use resolve*TourSteps() */
export const PROVIDERS_TOUR_STEPS = PROVIDERS_TOUR_STEP_DEFS;
/** @deprecated Use resolve*TourSteps() */
export const CRAWLER_TOUR_STEPS = CRAWLER_TOUR_STEP_DEFS;
