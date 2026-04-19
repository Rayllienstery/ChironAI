import { lazy, Suspense, useState, useEffect } from 'react';
import '../styles/components/TestingTab.css';
import CoreUIPillTabs from './CoreUIPillTabs';

const ModelTester = lazy(() => import('./ModelTester'));
const RagTestsTab = lazy(() => import('./RagTestsTab'));
const IndexerTester = lazy(() => import('./IndexerTester'));
const WebCallsTester = lazy(() => import('./WebCallsTester'));

const SUB_TABS = [
  { id: 'model-tester', label: 'Model Tester' },
  { id: 'rag-tests', label: 'RAG Tests' },
  { id: 'indexer-tester', label: 'Indexer Tester' },
  { id: 'web-calls', label: 'Web Calls' },
];

function TestingPanelFallback() {
  return <div className="loading">Loading testing tool...</div>;
}

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

  const handleSubTabClick = (id) => setSubTab(id);

  return (
    <div className="testing-tab">
      <div className="testing-tab-header">
        <h2>Testing</h2>
        <CoreUIPillTabs
          tabs={SUB_TABS}
          value={currentSubTab}
          onChange={handleSubTabClick}
          ariaLabel="Testing tools"
        />
      </div>
      <div className="testing-tab-content">
        <Suspense fallback={<TestingPanelFallback />}>
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
          {currentSubTab === 'web-calls' && <WebCallsTester />}
        </Suspense>
      </div>
    </div>
  );
}

export default TestingTab;
