import React, { useEffect, useState } from 'react';
import ClawProxyPanel from './ClawProxyPanel';
import ClawMcpPanel from './ClawMcpPanel';
import ClawProxyJournalTab from './ClawProxyJournalTab';
import '../styles/components/DashboardTab.css';
import '../styles/components/CoreUIPillTabs.css';

function ClawProxyTab({ onNavigateToRag, onModelStatusChange, focusSubTab, onFocusSubTabConsumed }) {
  const [subTab, setSubTab] = useState('proxy');

  useEffect(() => {
    if (!focusSubTab) return;
    setSubTab(focusSubTab);
    if (typeof onFocusSubTabConsumed === 'function') {
      onFocusSubTabConsumed();
    }
  }, [focusSubTab, onFocusSubTabConsumed]);

  return (
    <div className="dashboard-tab">
      <div className="claw-proxy-page-header">
        <h2>Claw Proxy</h2>
        <div className="coreui-pill-tablist" role="tablist" aria-label="Claw Proxy sections">
          <button
            type="button"
            className={`coreui-pill-tab ${subTab === 'proxy' ? 'coreui-pill-tab-active' : ''}`}
            role="tab"
            aria-selected={subTab === 'proxy'}
            onClick={() => setSubTab('proxy')}
          >
            Proxy
          </button>
          <button
            type="button"
            className={`coreui-pill-tab ${subTab === 'mcp' ? 'coreui-pill-tab-active' : ''}`}
            role="tab"
            aria-selected={subTab === 'mcp'}
            onClick={() => setSubTab('mcp')}
          >
            MCP
          </button>
          <button
            type="button"
            className={`coreui-pill-tab ${subTab === 'journal' ? 'coreui-pill-tab-active' : ''}`}
            role="tab"
            aria-selected={subTab === 'journal'}
            onClick={() => setSubTab('journal')}
          >
            Journal
          </button>
        </div>
      </div>
      {subTab === 'proxy' && (
        <ClawProxyPanel onNavigateToRag={onNavigateToRag} onModelStatusChange={onModelStatusChange} />
      )}
      {subTab === 'mcp' && <ClawMcpPanel />}
      {subTab === 'journal' && <ClawProxyJournalTab />}
    </div>
  );
}

export default ClawProxyTab;
