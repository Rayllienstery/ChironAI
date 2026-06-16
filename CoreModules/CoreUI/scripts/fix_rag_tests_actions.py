"""Rebuild useRagTestsActions.jsx from the corrupted split output."""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "components" / "ragTestsTab"
broken = (OUT / "useRagTestsActions.jsx").read_text(encoding="utf-8").splitlines(keepends=True)

start = next(i for i, line in enumerate(broken) if "const filteredTests" in line)
ret = next(i for i, line in enumerate(broken) if line.strip() == "return {")
body = "".join(broken[start:ret])
ret_block = "".join(broken[ret:])

header = """import { useEffect, useState } from 'react';
import {
  createRagTest,
  deleteRagTest,
  getRagTest,
  updateRagTest,
} from '../../services/api';
import { confirmCloudRagRun } from './helpers';

export function useRagTestsActions(core, {
  running = false,
  runProgress = null,
  results = [],
  runError = null,
  onStartRun,
  onCancelRun,
}) {
  const {
    tests,
    filters,
    selectedProviderId,
    selectedModel,
    selectedCollection,
    selectedPromptName,
    runTemperature,
    runTopK,
    runStrictMode,
    runConcurrency,
    selectedTestIds,
    setSelectedTestIds,
    setError,
    createForm,
    setCreateForm,
    setCreateOpen,
    setCreateSubmitting,
    setCreateConceptsWarning,
    editForm,
    setEditForm,
    setEditOpen,
    setEditTestId,
    setEditSubmitting,
    setEditConceptsWarning,
    collections,
    loadTests,
    liveMonitorDetailOpen,
    setLiveMonitorDetailOpen,
    liveDetailCardIndex,
    setLiveDetailCardIndex,
    currentStepStartedAt,
    liveNowMs,
    liveTrace,
    liveSse,
    setLiveMonitorOpen,
    resultDetailModal,
    setResultDetailModal,
    runHistoryModal,
    setRunHistoryModal,
    historySectionOpen,
    setHistorySectionOpen,
    runCompareModal,
    setRunCompareModal,
  } = core;

"""

# Return only keys not already provided by core
action_keys = """
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
"""

fixed = header + body + "  return {" + action_keys + "  };\n}\n"
(OUT / "useRagTestsActions.jsx").write_text(fixed, encoding="utf-8")
print("useRagTestsActions:", len(fixed.splitlines()), "lines")
