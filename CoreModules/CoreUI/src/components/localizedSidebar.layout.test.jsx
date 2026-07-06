import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import SidebarNav from './SidebarNav.jsx';
import { setLocale, t } from '../services/i18n.js';
import enCommon from '../../../Localization/localization/catalog/en/common.json';
import ukCommon from '../../../Localization/localization/catalog/uk/common.json';

function buildLocalizedTabs() {
  return [
    { id: 'dashboard', label: t('nav.dashboard'), section: 'Main' },
    { id: 'crawler', label: t('nav.crawler'), section: 'RAG' },
    { id: 'llm-proxy', label: t('nav.llm_proxy'), section: 'Core Functionality' },
    { id: 'rag', label: t('nav.rag'), section: 'RAG' },
    { id: 'extensions', label: t('nav.extensions'), section: 'Extensions' },
  ];
}

describe('localized sidebar layout', () => {
  beforeEach(() => {
    setLocale('uk');
  });

  it('uk catalog has the same keys as en', () => {
    expect(Object.keys(ukCommon).sort()).toEqual(Object.keys(enCommon).sort());
  });

  it('sidebar renders Ukrainian labels without horizontal overflow', () => {
    const tabs = buildLocalizedTabs();
    const { container } = render(
      <div style={{ width: 260, overflow: 'hidden' }}>
        <SidebarNav
          tabs={tabs}
          activeTab="dashboard"
          onTabChange={() => {}}
          collapsed={false}
        />
      </div>,
    );
    const nav = container.querySelector('.coreui-sidebar__nav');
    expect(nav).toBeTruthy();
    tabs.forEach((tab) => {
      expect(
        screen.getByRole('button', {
          name: new RegExp(tab.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')),
        }),
      ).toBeInTheDocument();
    });
    const shell = container.firstElementChild;
    if (shell) {
      expect(shell.scrollWidth).toBeLessThanOrEqual(shell.clientWidth + 1);
    }
  });
});
