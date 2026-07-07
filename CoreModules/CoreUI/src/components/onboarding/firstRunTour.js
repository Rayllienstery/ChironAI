/** First-run product tour — custom M3 engine (no @reactour/tour dependency). */

import { t } from '../../services/i18n';

const FIRST_RUN_TOUR_STEP_DEFS = [
  { id: 'language', kind: 'language' },
  {
    id: 'welcome',
    titleKey: 'onboarding.first_run.welcome.title',
    bodyKey: 'onboarding.first_run.welcome.body',
  },
  {
    id: 'dashboard',
    titleKey: 'onboarding.first_run.dashboard.title',
    bodyKey: 'onboarding.first_run.dashboard.body',
    target: '[data-tour="dashboard"]',
  },
  {
    id: 'builds',
    titleKey: 'onboarding.first_run.builds.title',
    bodyKey: 'onboarding.first_run.builds.body',
    target: '[data-tour="llm-proxy"]',
  },
  {
    id: 'providers',
    titleKey: 'onboarding.first_run.providers.title',
    bodyKey: 'onboarding.first_run.providers.body',
    target: '[data-tour="providers"]',
  },
  {
    id: 'help',
    titleKey: 'onboarding.first_run.help.title',
    bodyKey: 'onboarding.first_run.help.body',
    target: '[data-tour="help"]',
  },
  {
    id: 'settings',
    titleKey: 'onboarding.first_run.settings.title',
    bodyKey: 'onboarding.first_run.settings.body',
    target: '[data-tour="settings"]',
  },
];

export function resolveFirstRunTourSteps() {
  return FIRST_RUN_TOUR_STEP_DEFS.map((def) => {
    if (def.kind === 'language') {
      return {
        ...def,
        title: t('onboarding.language.title'),
        body: t('onboarding.language.body'),
      };
    }
    return {
      ...def,
      title: t(def.titleKey),
      body: t(def.bodyKey),
    };
  });
}
