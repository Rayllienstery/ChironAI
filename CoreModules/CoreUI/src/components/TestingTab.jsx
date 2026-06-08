import { lazy, Suspense, useState, useEffect } from 'react';
import '../styles/components/TestingTab.css';
import CoreUIPillTabs from './CoreUIPillTabs';
import { loadTrackedModule } from '../services/moduleTimings';

const ModelTester = lazy(() =>
  loadTrackedModule('ModelTester', () => import('./ModelTester'), { source: 'testing tab' })
);
const RagTestsTab = lazy(() =>
  loadTrackedModule('RagTestsTab', () => import('./RagTestsTab'), { source: 'testing tab' })
);
const RagTesterV2Tab = lazy(() =>
  loadTrackedModule('RagTesterV2Tab', () => import('./RagTesterV2Tab'), { source: 'testing tab' })
);
const IndexerTester = lazy(() =>
  loadTrackedModule('IndexerTester', () => import('./IndexerTester'), { source: 'testing tab' })
);
const WebCallsTester = lazy(() =>
  loadTrackedModule('WebCallsTester', () => import('./WebCallsTester'), { source: 'testing tab' })
);

const SUB_TABS = [
  { id: 'model-tester', label: 'Model Tester' },
  { id: 'rag-tests', label: 'RAG Tests' },
  { id: 'rag-tester-v2', label: 'Rag Tester V2' },
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
  pendingOpenRunId,
  onPendingOpenHandled,
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
    <div className="testing-tab tab-view">
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
              pendingOpenRunId={pendingOpenRunId}
              onPendingOpenHandled={onPendingOpenHandled}
              onStartRun={onStartRun}
              onCancelRun={onCancelRun}
            />
          )}
          {currentSubTab === 'rag-tester-v2' && <RagTesterV2Tab />}
          {currentSubTab === 'indexer-tester' && <IndexerTester />}
          {currentSubTab === 'web-calls' && <WebCallsTester />}
        </Suspense>
      </div>
    </div>
  );
}

export default TestingTab;
