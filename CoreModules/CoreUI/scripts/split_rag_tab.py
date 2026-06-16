"""Generate ragTab/ modules from RagTab.jsx (one-off split helper)."""
from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "ragTab"
OUT.mkdir(parents=True, exist_ok=True)
lines = (SRC / "RagTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


# --- constants.js ---
c = sl(33, 114)
c = c.replace("const ADVANCED_RETRIEVAL_OPTIONS", "export const ADVANCED_RETRIEVAL_OPTIONS", 1)
c += "\nexport const RAG_TABS = [\n  { id: 'main', label: 'Main' },\n  { id: 'collections', label: 'Collections' },\n  { id: 'settings', label: 'Settings' },\n];\n"
w("constants.js", c)

# --- helpers.js ---
helpers = sl(116, 152)
helpers = helpers.replace("function readMirroredRagTraceFromStorage", "export function readMirroredRagTraceFromStorage", 1)
helpers = helpers.replace("function wordsInMultipleCollections", "export function wordsInMultipleCollections", 1)
helpers = helpers.replace("function capitalize", "export function capitalize", 1)
helpers = (
    "import {\n"
    "  CHIRONAI_RAG_TRACE_STORAGE_KEY,\n"
    "} from '../RagTraceTimeline';\n\n"
    + helpers
)
w("helpers.js", helpers)

# --- useRagTab.js ---
use_rag = textwrap.dedent(
    """\
    import { useCallback, useEffect, useState } from 'react';
    import {
      checkRagTrigger,
      deleteRagKeywordCollection,
      getModelSettings,
      getProviderCatalog,
      getRagCollections,
      getRagFrameworkSettings,
      getRagKeywordCollections,
      getRagModelSettings,
      getRagStatus,
      getRagTriggerSettings,
      saveRagKeywordCollections,
      startRag,
      stopRag,
      updateModelSettings,
      updateRagFrameworkSettings,
      updateRagModelSettings,
      updateRagTriggerSettings,
    } from '../../services/api';
    import { useMergedPipelinePreview } from '../../hooks/useMergedPipelinePreview';
    import { CHIRONAI_RAG_TRACE_EVENT } from '../RagTraceTimeline';
    import { capitalize, readMirroredRagTraceFromStorage, wordsInMultipleCollections } from './helpers';

    export function useRagTab({ scrollToModelsSection, onModelsSectionScrolled }) {
    """
)
use_rag += sl(155, 665)
use_rag += textwrap.dedent(
    """
      return {
        activeTab,
        setActiveTab,
        loading,
        status,
        collections,
        keywordCollections,
        error,
        busy,
        sheetOpen,
        setSheetOpen,
        editCollectionId,
        editDraft,
        setEditDraft,
        addWordsCollectionId,
        setAddWordsCollectionId,
        addWordsList,
        addWordsInput,
        setAddWordsInput,
        deleteConfirmId,
        setDeleteConfirmId,
        savingKeywords,
        triggerSettings,
        triggerThresholdDraft,
        setTriggerThresholdDraft,
        triggerSaving,
        triggerTestMessage,
        setTriggerTestMessage,
        triggerTestResult,
        triggerTestLoading,
        frameworkSettings,
        frameworkTtlDraft,
        setFrameworkTtlDraft,
        savingFrameworkSettings,
        embedCatalog,
        rerankCatalog,
        ragModelSettings,
        setRagModelSettings,
        ragModelDefaults,
        retrievalYamlDefaults,
        ragModelSaving,
        ragModelSaveNotice,
        llmProxyRagSelect,
        setLlmProxyRagSelect,
        bindingsNotice,
        savingLlmRagBinding,
        pipelineMerged,
        mirroredPipelineTrace,
        embedProviders,
        embedModels,
        rerankProviders,
        rerankModels,
        filteredEmbedModels,
        filteredRerankModels,
        handleStart,
        handleStop,
        isRunning,
        overlappingWords,
        qdrantCollectionNames,
        saveLlmProxyRagBinding,
        handleSaveTriggerThreshold,
        handleCheckTrigger,
        handleSaveFrameworkSettings,
        handleSaveRagModelSettings,
        handleOpenDashboard,
        handleToggleEnabled,
        handleStartEdit,
        handleCancelEdit,
        handleSaveEdit,
        handleDeleteCollection,
        handleAddCollection,
        handlePasteIntoCollection,
        handleOpenAddWords,
        handleAddWordInputKeyDown,
        handleAddWordsSave,
        handleRefresh,
      };
    }
    """
)
w("useRagTab.js", use_rag)

# --- RagTabHeader.jsx ---
header = textwrap.dedent(
    """\
    import React from 'react';

    export default function RagTabHeader({
      isRunning,
      busy,
      status,
      onRefresh,
      onStartStop,
      onOpenDashboard,
    }) {
      return (
    """
) + sl(675, 708) + "\n  );\n}\n"
header = header.replace("onClick={handleRefresh}", "onClick={onRefresh}")
header = header.replace(
    "onClick={isRunning ? handleStop : handleStart}",
    "onClick={onStartStop}",
)
header = header.replace("onClick={handleOpenDashboard}", "onClick={onOpenDashboard}")
w("RagTabHeader.jsx", header)

# --- RagMainPanel.jsx ---
main_panel = textwrap.dedent(
    """\
    import React from 'react';
    import RagPipelineOverview from '../RagPipelineOverview';
    import RagTraceTimeline from '../RagTraceTimeline';

    export default function RagMainPanel({ status, ragModelSettings, mirroredPipelineTrace }) {
      return (
    """
) + sl(718, 792) + "\n  );\n}\n"
w("RagMainPanel.jsx", main_panel)

# --- RagSettingsPanel.jsx ---
settings = textwrap.dedent(
    """\
    import React from 'react';
    import Card from '../Card';
    import { ADVANCED_RETRIEVAL_OPTIONS } from './constants';

    export default function RagSettingsPanel({
      ragModelSettings,
      setRagModelSettings,
      ragModelDefaults,
      retrievalYamlDefaults,
      embedProviders,
      filteredEmbedModels,
      rerankProviders,
      filteredRerankModels,
      ragModelSaving,
      ragModelSaveNotice,
      handleSaveRagModelSettings,
      triggerSettings,
      triggerThresholdDraft,
      setTriggerThresholdDraft,
      triggerSaving,
      handleSaveTriggerThreshold,
      triggerTestMessage,
      setTriggerTestMessage,
      triggerTestResult,
      triggerTestLoading,
      handleCheckTrigger,
      overlappingWords,
      sheetOpen,
      setSheetOpen,
      llmProxyRagSelect,
      setLlmProxyRagSelect,
      qdrantCollectionNames,
      bindingsNotice,
      savingLlmRagBinding,
      saveLlmProxyRagBinding,
      frameworkSettings,
      frameworkTtlDraft,
      setFrameworkTtlDraft,
      savingFrameworkSettings,
      busy,
      handleSaveFrameworkSettings,
    }) {
      return (
    """
) + sl(794, 1301) + "\n  );\n}\n"
w("RagSettingsPanel.jsx", settings)

# --- RagCollectionsPanel.jsx ---
collections = textwrap.dedent(
    """\
    import React from 'react';

    export default function RagCollectionsPanel({
      loading,
      collections,
      frameworkSettings,
    }) {
      return (
    """
) + sl(1303, 1385) + "\n  );\n}\n"
w("RagCollectionsPanel.jsx", collections)

# --- RagKeywordsSheets.jsx ---
sheets = textwrap.dedent(
    """\
    import React from 'react';
    import Card from '../Card';

    export default function RagKeywordsSheets({
      sheetOpen,
      setSheetOpen,
      keywordCollections,
      savingKeywords,
      handleAddCollection,
      editCollectionId,
      editDraft,
      setEditDraft,
      handleToggleEnabled,
      handleSaveEdit,
      handleCancelEdit,
      handleStartEdit,
      handleOpenAddWords,
      handlePasteIntoCollection,
      deleteConfirmId,
      setDeleteConfirmId,
      handleDeleteCollection,
      addWordsCollectionId,
      setAddWordsCollectionId,
      addWordsInput,
      setAddWordsInput,
      addWordsList,
      handleAddWordInputKeyDown,
      handleAddWordsSave,
    }) {
      return (
        <>
    """
) + sl(1390, 1583) + "\n    </>\n  );\n}\n"
w("RagKeywordsSheets.jsx", sheets)

# --- RagTab.jsx (thin container) ---
container = textwrap.dedent(
    """\
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
    """
)
(SRC / "RagTab.jsx").write_text(container, encoding="utf-8")
print(f"RagTab.jsx: {len(container.splitlines())} lines")
print("Done.")
