"""Generate ragTestsTab/ modules from RagTestsTab.jsx."""
from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "ragTestsTab"
OUT.mkdir(parents=True, exist_ok=True)
lines = (SRC / "RagTestsTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


# --- constants.js ---
c = "export const RAG_TESTS_LAST_USED_KEY = 'coreui.rag_tests.last_used.v1';\n"
c += "export const LIVE_MONITOR_CLOCK_MS = 167;\n"
w("constants.js", c)

# --- helpers.js ---
helpers = (
    "import { RAG_TESTS_LAST_USED_KEY } from './constants';\n\n"
    + sl(30, 107)
    .replace("function modelTagLooksCloud", "export function modelTagLooksCloud", 1)
    .replace("function confirmCloudRagRun", "export function confirmCloudRagRun", 1)
    .replace("const RAG_TESTS_LAST_USED_KEY", "/* RAG_TESTS_LAST_USED_KEY in constants */", 1)
    .replace("const LIVE_MONITOR_CLOCK_MS", "/* LIVE_MONITOR_CLOCK_MS in constants */", 1)
    .replace("function ragRetrieved", "export function ragRetrieved", 1)
    .replace("function groundingOverlap", "export function groundingOverlap", 1)
    .replace("function strictRagOk", "export function strictRagOk", 1)
    .replace("function yesNo", "export function yesNo", 1)
    .replace("function metricVersionLabel", "export function metricVersionLabel", 1)
    .replace("function loadLastUsedRagTestsSettings", "export function loadLastUsedRagTestsSettings", 1)
    .replace("function sortModelsCloudFirst", "export function sortModelsCloudFirst", 1)
    .replace("function isTransientFetchLikeError", "export function isTransientFetchLikeError", 1)
)
w("helpers.js", helpers)

# --- useRagTestsTab.js ---
use_tab = textwrap.dedent(
    """\
    import { useCallback, useEffect, useState } from 'react';
    import {
      createRagTest,
      deleteRagTest,
      deleteRagTestRuns,
      exportRagTestRun,
      getPrompts,
      getProviderCatalog,
      getProxyTraceCurrent,
      getRagCollections,
      getRagTest,
      getRagTestRun,
      getRagTestRuns,
      getRagTestRunsSummary,
      getRagTests,
      updateRagTest,
    } from '../../services/api';
    import { isLogicalRagModelId } from '../../constants/llmProxyModels';
    import { LIVE_MONITOR_CLOCK_MS, RAG_TESTS_LAST_USED_KEY } from './constants';
    import {
      confirmCloudRagRun,
      isTransientFetchLikeError,
      loadLastUsedRagTestsSettings,
      sortModelsCloudFirst,
    } from './helpers';

    export function useRagTestsTab({
      runJobId = null,
      running = false,
      runProgress = null,
      results = [],
      runError = null,
      pendingOpenRunId = null,
      onPendingOpenHandled = null,
      onStartRun,
      onCancelRun,
    }) {
    """
)
use_tab += sl(120, 887)
use_tab += sl(888, 896)
use_tab += sl(897, 1012)
use_tab += textwrap.dedent(
    """
      return {
        providerCatalog,
        selectedProviderId,
        setSelectedProviderId,
        selectedModel,
        setSelectedModel,
        tests,
        filters,
        setFilters,
        filterOptions,
        error,
        setError,
        resultDetailModal,
        setResultDetailModal,
        selectedTestIds,
        createOpen,
        setCreateOpen,
        createForm,
        setCreateForm,
        createSubmitting,
        createConceptsWarning,
        editOpen,
        setEditOpen,
        editTestId,
        setEditTestId,
        editForm,
        setEditForm,
        editSubmitting,
        editConceptsWarning,
        runHistory,
        runHistoryLoading,
        runHistoryLoadingMore,
        runHistoryHasMore,
        historyFilters,
        setHistoryFilters,
        runSummary,
        runHistoryModal,
        setRunHistoryModal,
        runHistoryModalTab,
        setRunHistoryModalTab,
        historySectionOpen,
        setHistorySectionOpen,
        compareRunIds,
        runCompareLoading,
        runHistoryDeleteLoading,
        runCompareModal,
        setRunCompareModal,
        compareOnlyDiff,
        setCompareOnlyDiff,
        compareFocus,
        setCompareFocus,
        showFailDrilldown,
        setShowFailDrilldown,
        collections,
        selectedCollection,
        setSelectedCollection,
        prompts,
        selectedPromptName,
        setSelectedPromptName,
        runTemperature,
        setRunTemperature,
        runTopK,
        setRunTopK,
        runStrictMode,
        setRunStrictMode,
        runConcurrency,
        liveMonitorOpen,
        setLiveMonitorOpen,
        liveMonitorDetailOpen,
        setLiveMonitorDetailOpen,
        liveDetailCardIndex,
        setLiveDetailCardIndex,
        currentStepStartedAt,
        liveNowMs,
        liveTrace,
        liveSse,
        models,
        loadRunHistory,
        toggleCompareRun,
        clearCompareRuns,
        handleDeleteCancelledRuns,
        handleDeleteLowPassRuns,
        handleDeleteSelectedRuns,
        handleOpenRunCompare,
        handleSelectPastRun,
        filteredTests,
        canRun,
        hasActiveFilters,
        hasSelectedTests,
        runAllDisabled,
        runFilteredDisabled,
        runSelectedDisabled,
        handleRunAll,
        handleRunFiltered,
        handleRunSelected,
        handleRunSingle,
        handleCancelRun,
        toggleSelectTest,
        toggleSelectAll,
        handleCreateSubmit,
        handleEditClick,
        handleEditSubmit,
        handleDeleteClick,
        failFilters,
        setFailFilters,
        tableRows,
        currentStepElapsedMs,
        liveCards,
        formatSeconds,
        getLiveStepRows,
        timingLabel,
        renderTimingCards,
        selectedLiveDetailCard,
        selectedLiveStepRows,
        liveTraceChunks,
        liveTraceQuery,
        openLiveDetail,
        displayResults,
        failResults,
        running,
        runProgress,
        runError,
        onStartRun,
      };
    }
    """
)
w("useRagTestsTab.js", use_tab)

# --- useRagTestsDerived.js ---
derived = textwrap.dedent(
    """\
    import { useMemo } from 'react';
    import {
      groundingOverlap,
      metricVersionLabel,
      ragRetrieved,
      strictRagOk,
      yesNo,
    } from './helpers';

    export function useRagTestsDerived({
      runHistoryModal,
      runCompareModal,
      compareOnlyDiff,
      compareFocus,
      displayResults,
    }) {
    """
)
derived += sl(1013, 1400)
derived += textwrap.dedent(
    """
      return {
        runHistoryResults,
        latencyStatsMs,
        stageAvg,
        timingAverages,
        fastestTests,
        slowestTests,
        topChunks,
        mostPopularChunk,
        allFailureReasons,
        topFailureReasons,
        failureMaxCount,
        passCount,
        failCount,
        ragRetrievedCount,
        groundingOverlapCount,
        strictRagOkCount,
        strictRagTotal,
        totalCount,
        summaryBars,
        summaryBarMax,
        formatRunDate,
        compareLeftRun,
        compareRightRun,
        compareLeftResults,
        compareRightResults,
        compareSummaryRows,
        compareFmt,
        compareDeltaText,
        compareDeltaClass,
        compareConfidenceDeltaText,
        compareTpsDeltaText,
        compareSelectedDeltaText,
        compareHasTestDiff,
        compareVisiblePairs,
        compareRenderedPairs,
      };
    }
    """
)
w("useRagTestsDerived.js", derived)

# --- RagTestsRunPanel.jsx ---
run_panel = textwrap.dedent(
    """\
    import React from 'react';
    import Card from '../Card';
    import CoreUIButton from '../CoreUIButton';
    import CoreUISlider from '../CoreUISlider';

    export default function RagTestsRunPanel(props) {
      const {
        models,
        selectedProviderId,
        setSelectedProviderId,
        providerCatalog,
        selectedModel,
        setSelectedModel,
        collections,
        selectedCollection,
        setSelectedCollection,
        prompts,
        selectedPromptName,
        setSelectedPromptName,
        runConcurrency,
        setRunConcurrency,
        runStrictMode,
        setRunStrictMode,
        runTemperature,
        setRunTemperature,
        runTopK,
        setRunTopK,
        canRun,
        runAllDisabled,
        runFilteredDisabled,
        runSelectedDisabled,
        handleRunAll,
        handleRunFiltered,
        handleRunSelected,
        running,
        runProgress,
        handleCancelRun,
        error,
        runError,
      } = props;
      return (
    """
) + sl(1403, 1648) + "\n  );\n}\n"
w("RagTestsRunPanel.jsx", run_panel)

# --- RagTestsHistorySection.jsx ---
history = textwrap.dedent(
    """\
    import React from 'react';

    export default function RagTestsHistorySection(props) {
      return (
    """
) + sl(1650, 1927) + "\n  );\n}\n"
w("RagTestsHistorySection.jsx", history)

# --- RagTestsLiveSection.jsx ---
live = textwrap.dedent(
    """\
    import React from 'react';
    import Card from '../Card';

    export default function RagTestsLiveSection(props) {
      return (
    """
) + sl(1929, 2063) + "\n  );\n}\n"
w("RagTestsLiveSection.jsx", live)
# live detail modal lines 1993-2063 included in live section

# --- RagTestsTableSection.jsx ---
table = textwrap.dedent(
    """\
    import React from 'react';
    import Card from '../Card';
    import { ragRetrieved, yesNo } from './helpers';

    export default function RagTestsTableSection(props) {
      return (
    """
) + sl(2065, 2230) + "\n" + sl(2653, 2770) + "\n  );\n}\n"
w("RagTestsTableSection.jsx", table)

# --- RagTestsModalsSection.jsx ---
modals = textwrap.dedent(
    """\
    import React from 'react';
    import { RagResultDetailModal, RagTestFormModal } from '../RagTestsModals';
    import { metricVersionLabel, ragRetrieved, yesNo } from './helpers';

    export default function RagTestsModalsSection(props) {
      return (
        <>
    """
) + sl(2232, 2651) + "\n" + sl(2771, 2799) + "\n    </>\n  );\n}\n"
w("RagTestsModalsSection.jsx", modals)

# --- RagTestsTab.jsx ---
container = textwrap.dedent(
    """\
    import React from 'react';
    import '../styles/components/CoreUIButtons.css';
    import '../styles/components/RagTestsTab.css';
    import RagTestsHistorySection from './ragTestsTab/RagTestsHistorySection';
    import RagTestsLiveSection from './ragTestsTab/RagTestsLiveSection';
    import RagTestsModalsSection from './ragTestsTab/RagTestsModalsSection';
    import RagTestsRunPanel from './ragTestsTab/RagTestsRunPanel';
    import RagTestsTableSection from './ragTestsTab/RagTestsTableSection';
    import { useRagTestsDerived } from './ragTestsTab/useRagTestsDerived';
    import { useRagTestsTab } from './ragTestsTab/useRagTestsTab';

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
    """
)
(SRC / "RagTestsTab.jsx").write_text(container, encoding="utf-8")
print(f"RagTestsTab.jsx: {len(container.splitlines())} lines")
print("Done.")
