import React, { useState, useEffect } from 'react';
import ModelTester from './ModelTester';
import RagTestsTab from './RagTestsTab';
import IndexerTester from './IndexerTester';
import '../styles/components/TestingTab.css';

const SUB_TABS = [
  { id: 'model-tester', label: 'Model Tester' },
  { id: 'rag-tests', label: 'RAG Tests' },
  { id: 'indexer-tester', label: 'Indexer Tester' },
];

function TestingTab({
  sessionId,
  activeSubTab,
  onSubTabChange,
  runJobId,
  running,
  runProgress,
  results,
  runError,
  onStartRun,
  onCancelRun,
}) {
  const [internalSubTab, setInternalSubTab] = useState('model-tester');
  const isControlled = activeSubTab != null && typeof onSubTabChange === 'function';
  const currentSubTab = isControlled ? activeSubTab : internalSubTab;
  const setSubTab = isControlled ? onSubTabChange : setInternalSubTab;

  useEffect(() => {
    if (isControlled && activeSubTab != null) {
      setInternalSubTab(activeSubTab);
    }
  }, [isControlled, activeSubTab]);

  useEffect(() => {
    if (isControlled && activeSubTab === 'claw-proxy' && typeof onSubTabChange === 'function') {
      onSubTabChange('rag-tests');
    }
  }, [isControlled, activeSubTab, onSubTabChange]);

  const handleSubTabClick = (id) => setSubTab(id);

  return (
    <div className="testing-tab">
      <div className="testing-tab-header">
        <h2>Testing</h2>
        <div className="testing-subtabs" role="tablist" aria-label="Testing tools">
          {SUB_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`testing-subtab ${currentSubTab === tab.id ? 'testing-subtab-active' : ''}`}
              role="tab"
              aria-selected={currentSubTab === tab.id}
              onClick={() => handleSubTabClick(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="testing-tab-content">
        {currentSubTab === 'model-tester' && <ModelTester sessionId={sessionId} />}
        {currentSubTab === 'rag-tests' && (
          <RagTestsTab
            runJobId={runJobId}
            running={running}
            runProgress={runProgress}
            results={results}
            runError={runError}
            onStartRun={onStartRun}
            onCancelRun={onCancelRun}
          />
        )}
        {currentSubTab === 'indexer-tester' && <IndexerTester />}
      </div>
    </div>
  );
}

export default TestingTab;
