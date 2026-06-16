"""Generate useCreateCollectionFlow and useMdPipelineSection hooks."""
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "crawlerTab"
lines = (SRC / "CrawlerTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


create_hook = textwrap.dedent(
    """\
    import React, { useCallback, useEffect, useRef, useState } from "react";
    import CreateCollectionIndexProgress, {
      createCollectionFinalLogMetadata,
      formatDurationMs,
    } from "../CreateCollectionIndexProgress";
    import {
      cancelCreateCollection,
      createCollection,
      getCreateCollectionStatus,
      getProviderCatalog,
      getRagModelSettings,
    } from "../../services/api";
    import {
      CREATE_COLLECTION_LIVE_ID,
      CREATE_COLLECTION_POLL_INTERVAL_MS,
    } from "./constants";

    export function useCreateCollectionFlow({
      nc,
      activeSection,
      sources,
      setError,
      loadCollections,
    }) {
    """
)
create_hook += sl(156, 179)
create_hook += "  const createPersistedJobRef = useRef(null);\n"
create_hook += sl(273, 525)
create_hook += sl(1002, 1096)
create_hook += sl(1098, 1111)
create_hook += sl(1113, 1169)
create_hook += sl(1194, 1201)

create_hook += textwrap.dedent(
    """
      return {
        showCreateModal,
        setShowCreateModal,
        createForm,
        setCreateForm,
        createEmbedCatalog,
        createEmbedDefaults,
        creating,
        createJobId,
        createProgress,
        createCanceling,
        showCreateToast,
        createCollectionName,
        createCollectionToastName,
        createCollectionToastTitle,
        createCollectionLiveSuppressed,
        showCreateCollectionDetailsAction,
        handleCreateCollection,
        handleCancelCreateCollection,
        handleOpenCreateCollectionDetails,
        toggleSourceInForm,
      };
    }
    """
)
w("useCreateCollectionFlow.js", create_hook)

md_hook = textwrap.dedent(
    """\
    import { useEffect, useState } from "react";
    import {
      deleteMdPipeline,
      getIndexerTesterFiles,
      getIndexerTesterSources,
      getMdPipeline,
      getMdPipelines,
      previewMdPipeline,
      saveMdPipeline,
    } from "../../services/api";
    import { getDefaultParamsForStepType } from "./helpers";

    export function useMdPipelineSection({ activeSection }) {
    """
)
md_hook += sl(209, 232)
md_hook += sl(650, 990)
md_hook += textwrap.dedent(
    """
      return {
        pipelineList,
        selectedPipelineName,
        setSelectedPipelineName,
        pipelineData,
        setPipelineData,
        pipelineLoading,
        pipelineError,
        pipelineSaving,
        pipelineSaveToast,
        showAddStepMenu,
        setShowAddStepMenu,
        previewResult,
        setPreviewResult,
        previewLoading,
        showCreatePipelineModal,
        setShowCreatePipelineModal,
        newPipelineName,
        setNewPipelineName,
        showDeletePipelineConfirm,
        setShowDeletePipelineConfirm,
        pipelinePreviewSources,
        pipelinePreviewSourceId,
        setPipelinePreviewSourceId,
        pipelinePreviewFiles,
        pipelinePreviewFilename,
        setPipelinePreviewFilename,
        pipelinePreviewSourcesLoading,
        pipelinePreviewFilesLoading,
        expandedMdSteps,
        handleSaveMdPipeline,
        handleAddMdStep,
        toggleMdStepExpanded,
        handleChangeMdStepType,
        handleRemoveMdStep,
        handleMoveMdStep,
        handleUpdateMdStep,
        addMdStepLine,
        removeMdStepLine,
        updateMdStepLine,
        handlePreviewMdPipeline,
        handleCreatePipeline,
        handleConfirmCreatePipeline,
        handleDeletePipelineClick,
        handleConfirmDeletePipeline,
      };
    }
    """
)
w("useMdPipelineSection.js", md_hook)

print("Generated remaining hooks")
