"""Split useRagTestsTab hook from git RagTestsTab.jsx into core + actions."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "components" / "ragTestsTab"
REPO = ROOT.parents[1]
orig = subprocess.check_output(
    ["git", "show", "HEAD:CoreModules/CoreUI/src/components/RagTestsTab.jsx"],
    cwd=REPO,
    text=True,
)
lines = orig.splitlines(keepends=True)

hook_start = next(i for i, line in enumerate(lines) if line.startswith("function RagTestsTab"))
body_start = next(i for i, line in enumerate(lines) if line.strip() == "}) {" and i >= hook_start) + 1
props_inner = "".join(lines[hook_start + 1 : body_start - 1])
idx = next(i for i, line in enumerate(lines) if "const filteredTests" in line)
ret = next(i for i, line in enumerate(lines) if line.strip().startswith("const runHistoryResults ="))

core_body = "".join(lines[body_start:idx])
actions_body = "".join(lines[idx:ret])

header = """import { useCallback, useEffect, useState } from 'react';
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

"""

core = header + "export function useRagTestsCore({\n" + props_inner + "}) {\n" + core_body
core += "  return {\n"
core += "    providerCatalog, selectedProviderId, setSelectedProviderId,\n"
core += "    selectedModel, setSelectedModel, tests, filters, setFilters, filterOptions,\n"
core += "    error, setError, resultDetailModal, setResultDetailModal, selectedTestIds,\n"
core += "    createOpen, setCreateOpen, createForm, setCreateForm, createSubmitting, createConceptsWarning,\n"
core += "    editOpen, setEditOpen, editTestId, setEditTestId, editForm, setEditForm,\n"
core += "    editSubmitting, editConceptsWarning, runHistory, runHistoryLoading, runHistoryLoadingMore,\n"
core += "    runHistoryHasMore, historyFilters, setHistoryFilters, runSummary, runHistoryModal,\n"
core += "    setRunHistoryModal, runHistoryModalTab, setRunHistoryModalTab, historySectionOpen,\n"
core += "    setHistorySectionOpen, compareRunIds, setCompareRunIds, runCompareLoading, setRunCompareLoading,\n"
core += "    runHistoryDeleteLoading, setRunHistoryDeleteLoading, runCompareModal, setRunCompareModal,\n"
core += "    compareOnlyDiff, setCompareOnlyDiff, compareFocus, setCompareFocus, showFailDrilldown,\n"
core += "    setShowFailDrilldown, collections, selectedCollection, setSelectedCollection, prompts,\n"
core += "    selectedPromptName, setSelectedPromptName, runTemperature, setRunTemperature, runTopK,\n"
core += "    setRunTopK, runStrictMode, setRunStrictMode, runConcurrency, liveMonitorOpen,\n"
core += "    setLiveMonitorOpen, liveMonitorDetailOpen, setLiveMonitorDetailOpen, liveDetailCardIndex,\n"
core += "    setLiveDetailCardIndex, currentStepStartedAt, setCurrentStepStartedAt, liveNowMs,\n"
core += "    setLiveNowMs, liveTrace, setLiveTrace, liveSse, setLiveSse, models, loadRunHistory,\n"
core += "    loadTests, toggleCompareRun, clearCompareRuns, handleDeleteCancelledRuns,\n"
core += "    handleDeleteLowPassRuns, handleDeleteSelectedRuns, handleOpenRunCompare, handleSelectPastRun,\n"
core += "  };\n}\n"

actions_header = """import { useEffect, useState } from 'react';
import {
  createRagTest,
  deleteRagTest,
  getRagTest,
  updateRagTest,
} from '../../services/api';
import { confirmCloudRagRun } from './helpers';

"""

actions = actions_header + "export function useRagTestsActions(core, {\n" + props_inner + "}) {\n"
actions += "  const {\n"
actions += "    tests, filters, selectedProviderId, selectedModel, selectedCollection,\n"
actions += "    selectedPromptName, runTemperature, runTopK, runStrictMode, runConcurrency,\n"
actions += "    selectedTestIds, setSelectedTestIds, setError, createForm, setCreateForm,\n"
actions += "    setCreateOpen, setCreateSubmitting, setCreateConceptsWarning, editForm, setEditForm,\n"
actions += "    setEditOpen, setEditTestId, setEditSubmitting, setEditConceptsWarning, collections,\n"
actions += "    loadTests, liveMonitorDetailOpen, setLiveMonitorDetailOpen, liveDetailCardIndex,\n"
actions += "    setLiveDetailCardIndex, currentStepStartedAt, liveNowMs, liveTrace, liveSse,\n"
actions += "    resultDetailModal, setResultDetailModal, runHistoryModal, setRunHistoryModal,\n"
actions += "    historySectionOpen, setHistorySectionOpen, runCompareModal, setRunCompareModal,\n"
actions += "  } = core;\n\n"
actions += actions_body
actions += "  return {\n"
actions += "    filteredTests, canRun, hasActiveFilters, hasSelectedTests,\n"
actions += "    runAllDisabled, runFilteredDisabled, runSelectedDisabled,\n"
actions += "    handleRunAll, handleRunFiltered, handleRunSelected, handleRunSingle, handleCancelRun,\n"
actions += "    toggleSelectTest, toggleSelectAll, handleCreateSubmit, handleEditClick, handleEditSubmit,\n"
actions += "    handleDeleteClick, failFilters, setFailFilters, tableRows, currentStepElapsedMs,\n"
actions += "    liveCards, formatSeconds, getLiveStepRows, timingLabel, renderTimingCards,\n"
actions += "    selectedLiveDetailCard, selectedLiveStepRows, liveTraceChunks, liveTraceQuery,\n"
actions += "    openLiveDetail, displayResults, failResults, running, runProgress, runError, onStartRun,\n"
actions += "  };\n}\n"

composer = """import { useRagTestsActions } from './useRagTestsActions.jsx';
import { useRagTestsCore } from './useRagTestsCore.jsx';

export function useRagTestsTab(props) {
  const core = useRagTestsCore(props);
  const actions = useRagTestsActions(core, props);
  return { ...core, ...actions };
}
"""

(OUT / "useRagTestsCore.jsx").write_text(core, encoding="utf-8")
(OUT / "useRagTestsActions.jsx").write_text(actions, encoding="utf-8")
(OUT / "useRagTestsTab.jsx").write_text(composer, encoding="utf-8")
print("useRagTestsCore:", len(core.splitlines()), "useRagTestsActions:", len(actions.splitlines()))
