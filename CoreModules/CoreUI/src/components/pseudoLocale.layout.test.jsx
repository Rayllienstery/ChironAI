import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import SidebarNav from './SidebarNav.jsx';
import { setLocale, t } from '../services/i18n.js';
import enCommon from '../../../Localization/localization/catalog/en/common.json';
import enXaCommon from '../../../Localization/localization/catalog/en-XA/common.json';

function buildPseudoLocaleTabs() {
  return [
    { id: 'dashboard', label: t('nav.dashboard'), section: 'Main' },
    { id: 'crawler', label: t('nav.crawler'), section: 'RAG' },
    { id: 'llm-proxy', label: t('nav.llm_proxy'), section: 'Core Functionality' },
    { id: 'rag', label: t('nav.rag'), section: 'RAG' },
    { id: 'extensions', label: t('nav.extensions'), section: 'Extensions' },
  ];
}

describe('pseudo-locale layout', () => {
  beforeEach(() => {
    setLocale('en-XA');
  });

  it('en-XA catalog has the same keys as en', () => {
    expect(Object.keys(enXaCommon).sort()).toEqual(Object.keys(enCommon).sort());
  });

  it('pseudo-locale nav labels are longer than en', () => {
    setLocale('en');
    const enLabel = t('nav.llm_proxy');
    setLocale('en-XA');
    expect(t('nav.llm_proxy').length).toBeGreaterThan(enLabel.length);
  });

  it('sidebar renders pseudo-locale labels without horizontal overflow', () => {
    const tabs = buildPseudoLocaleTabs();
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
      expect(screen.getByRole('button', { name: new RegExp(tab.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) })).toBeInTheDocument();
    });
    const shell = container.firstElementChild;
    if (shell) {
      expect(shell.scrollWidth).toBeLessThanOrEqual(shell.clientWidth + 1);
    }
  });
});
