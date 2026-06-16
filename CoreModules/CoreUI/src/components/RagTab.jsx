import React from 'react';
import CoreUIPillTabs from './CoreUIPillTabs';
import '../styles/components/CoreUIButtons.css';
import '../styles/components/RagTab.css';
import { RAG_TABS } from './ragTab/constants';
import RagCollectionsPanel from './ragTab/RagCollectionsPanel';
import RagKeywordsSheets from './ragTab/RagKeywordsSheets';
import RagMainPanel from './ragTab/RagMainPanel';
import RagSettingsPanel from './ragTab/RagSettingsPanel';
import RagTabHeader from './ragTab/RagTabHeader';
import { useRagTab } from './ragTab/useRagTab';

function RagTab({ scrollToModelsSection, onModelsSectionScrolled }) {
  const rag = useRagTab({ scrollToModelsSection, onModelsSectionScrolled });

  return (
    <div className="rag-tab tab-view">
      <RagTabHeader
        isRunning={rag.isRunning}
        busy={rag.busy}
        status={rag.status}
        onRefresh={rag.handleRefresh}
        onStartStop={rag.isRunning ? rag.handleStop : rag.handleStart}
        onOpenDashboard={rag.handleOpenDashboard}
      />

      <div className="rag-tabs-nav">
        <CoreUIPillTabs
          tabs={RAG_TABS}
          value={rag.activeTab}
          onChange={rag.setActiveTab}
        />
      </div>

      {rag.activeTab === 'main' && (
        <RagMainPanel
          status={rag.status}
          ragModelSettings={rag.ragModelSettings}
          mirroredPipelineTrace={rag.mirroredPipelineTrace}
        />
      )}

      {rag.activeTab === 'settings' && (
        <RagSettingsPanel
          ragModelSettings={rag.ragModelSettings}
          setRagModelSettings={rag.setRagModelSettings}
          ragModelDefaults={rag.ragModelDefaults}
          retrievalYamlDefaults={rag.retrievalYamlDefaults}
          embedProviders={rag.embedProviders}
          filteredEmbedModels={rag.filteredEmbedModels}
          rerankProviders={rag.rerankProviders}
          filteredRerankModels={rag.filteredRerankModels}
          ragModelSaving={rag.ragModelSaving}
          ragModelSaveNotice={rag.ragModelSaveNotice}
          handleSaveRagModelSettings={rag.handleSaveRagModelSettings}
          triggerSettings={rag.triggerSettings}
          triggerThresholdDraft={rag.triggerThresholdDraft}
          setTriggerThresholdDraft={rag.setTriggerThresholdDraft}
          triggerSaving={rag.triggerSaving}
          handleSaveTriggerThreshold={rag.handleSaveTriggerThreshold}
          triggerTestMessage={rag.triggerTestMessage}
          setTriggerTestMessage={rag.setTriggerTestMessage}
          triggerTestResult={rag.triggerTestResult}
          triggerTestLoading={rag.triggerTestLoading}
          handleCheckTrigger={rag.handleCheckTrigger}
          overlappingWords={rag.overlappingWords}
          sheetOpen={rag.sheetOpen}
          setSheetOpen={rag.setSheetOpen}
          llmProxyRagSelect={rag.llmProxyRagSelect}
          setLlmProxyRagSelect={rag.setLlmProxyRagSelect}
          qdrantCollectionNames={rag.qdrantCollectionNames}
          bindingsNotice={rag.bindingsNotice}
          savingLlmRagBinding={rag.savingLlmRagBinding}
          saveLlmProxyRagBinding={rag.saveLlmProxyRagBinding}
          frameworkSettings={rag.frameworkSettings}
          frameworkTtlDraft={rag.frameworkTtlDraft}
          setFrameworkTtlDraft={rag.setFrameworkTtlDraft}
          savingFrameworkSettings={rag.savingFrameworkSettings}
          busy={rag.busy}
          handleSaveFrameworkSettings={rag.handleSaveFrameworkSettings}
        />
      )}

      {rag.activeTab === 'collections' && (
        <RagCollectionsPanel
          loading={rag.loading}
          collections={rag.collections}
          frameworkSettings={rag.frameworkSettings}
        />
      )}

      {rag.error && <div className="rag-error">Error: {rag.error}</div>}

      <RagKeywordsSheets
        sheetOpen={rag.sheetOpen}
        setSheetOpen={rag.setSheetOpen}
        keywordCollections={rag.keywordCollections}
        savingKeywords={rag.savingKeywords}
        handleAddCollection={rag.handleAddCollection}
        editCollectionId={rag.editCollectionId}
        editDraft={rag.editDraft}
        setEditDraft={rag.setEditDraft}
        handleToggleEnabled={rag.handleToggleEnabled}
        handleSaveEdit={rag.handleSaveEdit}
        handleCancelEdit={rag.handleCancelEdit}
        handleStartEdit={rag.handleStartEdit}
        handleOpenAddWords={rag.handleOpenAddWords}
        handlePasteIntoCollection={rag.handlePasteIntoCollection}
        deleteConfirmId={rag.deleteConfirmId}
        setDeleteConfirmId={rag.setDeleteConfirmId}
        handleDeleteCollection={rag.handleDeleteCollection}
        addWordsCollectionId={rag.addWordsCollectionId}
        setAddWordsCollectionId={rag.setAddWordsCollectionId}
        addWordsInput={rag.addWordsInput}
        setAddWordsInput={rag.setAddWordsInput}
        addWordsList={rag.addWordsList}
        handleAddWordInputKeyDown={rag.handleAddWordInputKeyDown}
        handleAddWordsSave={rag.handleAddWordsSave}
      />
    </div>
  );
}

export default RagTab;
