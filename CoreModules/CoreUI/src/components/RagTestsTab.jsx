import React from 'react';
import '../styles/components/CoreUIButtons.css';
import '../styles/components/RagTestsTab.css';
import RagTestsHistorySection from './ragTestsTab/RagTestsHistorySection';
import RagTestsLiveSection from './ragTestsTab/RagTestsLiveSection';
import RagTestsModalsSection from './ragTestsTab/RagTestsModalsSection';
import RagTestsRunPanel from './ragTestsTab/RagTestsRunPanel';
import RagTestsTableSection from './ragTestsTab/RagTestsTableSection';
import { useRagTestsDerived } from './ragTestsTab/useRagTestsDerived';
import { useRagTestsTab } from './ragTestsTab/useRagTestsTab.jsx';

function RagTestsTab(props) {
  const tab = useRagTestsTab(props);
  const derived = useRagTestsDerived({
    runHistoryModal: tab.runHistoryModal,
    runCompareModal: tab.runCompareModal,
    compareOnlyDiff: tab.compareOnlyDiff,
    compareFocus: tab.compareFocus,
    displayResults: tab.displayResults,
  });
  const view = { ...tab, ...derived };

  return (
    <div className="rag-tests-tab">
      <RagTestsRunPanel {...view} />
      <RagTestsHistorySection {...view} />
      <RagTestsLiveSection {...view} />
      <RagTestsTableSection {...view} />
      <RagTestsModalsSection {...view} />
    </div>
  );
}

export default RagTestsTab;
