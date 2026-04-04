import React, { useState } from 'react';
import ClawProxyPanel from './ClawProxyPanel';
import ClawMcpPanel from './ClawMcpPanel';
import ClawProxyJournalTab from './ClawProxyJournalTab';
import '../styles/components/DashboardTab.css';
import '../styles/components/TestingTab.css';

function ClawProxyTab({ onModelStatusChange }) {
  const [subTab, setSubTab] = useState('proxy');

  return (
    <div className="dashboard-tab">
      <div className="claw-proxy-page-header">
        <h2>Claw Proxy</h2>
        <div className="testing-subtabs" role="tablist" aria-label="Claw Proxy sections">
          <button
            type="button"
            className={`testing-subtab ${subTab === 'proxy' ? 'testing-subtab-active' : ''}`}
            role="tab"
            aria-selected={subTab === 'proxy'}
            onClick={() => setSubTab('proxy')}
          >
            Proxy
          </button>
          <button
            type="button"
            className={`testing-subtab ${subTab === 'mcp' ? 'testing-subtab-active' : ''}`}
            role="tab"
            aria-selected={subTab === 'mcp'}
            onClick={() => setSubTab('mcp')}
          >
            MCP
          </button>
          <button
            type="button"
            className={`testing-subtab ${subTab === 'journal' ? 'testing-subtab-active' : ''}`}
            role="tab"
            aria-selected={subTab === 'journal'}
            onClick={() => setSubTab('journal')}
          >
            Journal
          </button>
        </div>
      </div>
      {subTab === 'proxy' && <ClawProxyPanel onModelStatusChange={onModelStatusChange} />}
      {subTab === 'mcp' && <ClawMcpPanel />}
      {subTab === 'journal' && <ClawProxyJournalTab />}
    </div>
  );
}

export default ClawProxyTab;
