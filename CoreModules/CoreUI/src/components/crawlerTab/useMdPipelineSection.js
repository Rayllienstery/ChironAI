import { useEffect, useState } from "react";
import { t } from "../../services/i18n.js";
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
  // MD Pipeline state
  const [pipelineList, setPipelineList] = useState([]);
  const [selectedPipelineName, setSelectedPipelineName] = useState("");
  const [pipelineData, setPipelineData] = useState({ name: "", steps: [] });
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState(null);
  const [pipelineSaving, setPipelineSaving] = useState(false);
  const [pipelineSaveToast, setPipelineSaveToast] = useState(false);
  const [showAddStepMenu, setShowAddStepMenu] = useState(false);
  const [previewResult, setPreviewResult] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [showCreatePipelineModal, setShowCreatePipelineModal] = useState(false);
  const [newPipelineName, setNewPipelineName] = useState("");
  const [showDeletePipelineConfirm, setShowDeletePipelineConfirm] =
    useState(false);
  const [pipelinePreviewSources, setPipelinePreviewSources] = useState([]);
  const [pipelinePreviewSourceId, setPipelinePreviewSourceId] = useState("");
  const [pipelinePreviewFiles, setPipelinePreviewFiles] = useState([]);
  const [pipelinePreviewFilename, setPipelinePreviewFilename] = useState("");
  const [pipelinePreviewSourcesLoading, setPipelinePreviewSourcesLoading] =
    useState(false);
  const [pipelinePreviewFilesLoading, setPipelinePreviewFilesLoading] =
    useState(false);
  const [expandedMdSteps, setExpandedMdSteps] = useState(new Set());
  const loadPipelinePreviewSources = async () => {
    setPipelinePreviewSourcesLoading(true);
    setPipelineError(null);
    try {
      const data = await getIndexerTesterSources();
      const list = data.sources || [];
      setPipelinePreviewSources(list);
      setPipelinePreviewSourceId((prev) => {
        if (prev && list.some((s) => s.id === prev)) return prev;
        return list.length > 0 ? list[0].id : "";
      });
      setPipelinePreviewFiles([]);
      setPipelinePreviewFilename("");
    } catch (e) {
      setPipelineError(e.message);
      setPipelinePreviewSources([]);
      setPipelinePreviewSourceId("");
    } finally {
      setPipelinePreviewSourcesLoading(false);
    }
  };

  const loadPipelinePreviewFiles = async (sourceId) => {
    if (!sourceId) {
      setPipelinePreviewFiles([]);
      setPipelinePreviewFilename("");
      return;
    }
    setPipelinePreviewFilesLoading(true);
    setPipelineError(null);
    try {
      const data = await getIndexerTesterFiles(sourceId, {
        sortBy: "name",
        order: "asc",
      });
      const files = data.files || [];
      setPipelinePreviewFiles(files);
      setPipelinePreviewFilename((prev) => {
        if (prev && files.some((f) => f.filename === prev)) return prev;
        return files.length > 0 ? files[0].filename : "";
      });
    } catch (e) {
      setPipelineError(e.message);
      setPipelinePreviewFiles([]);
      setPipelinePreviewFilename("");
    } finally {
      setPipelinePreviewFilesLoading(false);
    }
  };

  const loadMdPipelinesList = async () => {
    setPipelineError(null);
    try {
      const data = await getMdPipelines();
      const list = data.pipelines || [];
      setPipelineList(list);
      if (list.length > 0 && !selectedPipelineName) {
        setSelectedPipelineName(list[0]);
      }
      return list;
    } catch (e) {
      setPipelineError(e.message);
      setPipelineList([]);
      return [];
    }
  };

  const loadMdPipelineBody = async (name) => {
    if (!name) {
      setPipelineData({ name: "", steps: [] });
      return;
    }
    setPipelineLoading(true);
    setPipelineError(null);
    try {
      const data = await getMdPipeline(name);
      setPipelineData({
        name: data.name || name,
        steps: Array.isArray(data.steps) ? data.steps : [],
      });
    } catch (e) {
      setPipelineError(e.message);
      setPipelineData({ name: "", steps: [] });
    } finally {
      setPipelineLoading(false);
    }
  };

  const handleSaveMdPipeline = async () => {
    if (!selectedPipelineName) return;
    setPipelineSaving(true);
    setPipelineError(null);
    try {
      await saveMdPipeline(selectedPipelineName, {
        name: pipelineData.name || selectedPipelineName,
        steps: pipelineData.steps,
      });
      setPipelineSaveToast(true);
      setTimeout(() => setPipelineSaveToast(false), 2000);
    } catch (e) {
      setPipelineError(e.message);
    } finally {
      setPipelineSaving(false);
    }
  };

  const handleAddMdStep = (type) => {
    const id = `step-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const step = { id, type, params: getDefaultParamsForStepType(type) };
    setPipelineData((prev) => ({ ...prev, steps: [...prev.steps, step] }));
    setShowAddStepMenu(false);
  };

  const toggleMdStepExpanded = (key) => {
    setExpandedMdSteps((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleChangeMdStepType = (index, newType) => {
    if (newType === pipelineData.steps[index]?.type) return;
    setPipelineData((prev) => {
      const steps = [...prev.steps];
      steps[index] = {
        ...steps[index],
        type: newType,
        params: getDefaultParamsForStepType(newType),
      };
      return { ...prev, steps };
    });
  };

  const handleRemoveMdStep = (index) => {
    setPipelineData((prev) => ({
      ...prev,
      steps: prev.steps.filter((_, i) => i !== index),
    }));
  };

  const handleMoveMdStep = (index, direction) => {
    if (direction < 0 && index <= 0) return;
    if (direction > 0 && index >= pipelineData.steps.length - 1) return;
    const newSteps = [...pipelineData.steps];
    const swap = index + direction;
    [newSteps[index], newSteps[swap]] = [newSteps[swap], newSteps[index]];
    setPipelineData((prev) => ({ ...prev, steps: newSteps }));
  };

  const handleUpdateMdStep = (index, patch) => {
    setPipelineData((prev) => {
      const steps = [...prev.steps];
      steps[index] = { ...steps[index], ...patch };
      return { ...prev, steps };
    });
  };

  const updateMdStepArrayParam = (stepIndex, paramKey, updater) => {
    setPipelineData((prev) => {
      const steps = [...prev.steps];
      const step = steps[stepIndex];
      const arr = step.params?.[paramKey] ?? [];
      steps[stepIndex] = {
        ...step,
        params: {
          ...step.params,
          [paramKey]: updater(Array.isArray(arr) ? arr : []),
        },
      };
      return { ...prev, steps };
    });
  };

  const addMdStepLine = (stepIndex, paramKey) => {
    updateMdStepArrayParam(stepIndex, paramKey, (arr) => [...arr, ""]);
  };

  const removeMdStepLine = (stepIndex, paramKey, lineIndex) => {
    updateMdStepArrayParam(stepIndex, paramKey, (arr) =>
      arr.filter((_, i) => i !== lineIndex),
    );
  };

  const updateMdStepLine = (stepIndex, paramKey, lineIndex, value) => {
    updateMdStepArrayParam(stepIndex, paramKey, (arr) =>
      arr.map((item, i) => (i === lineIndex ? value : item)),
    );
  };

  const handlePreviewMdPipeline = async () => {
    if (!pipelinePreviewSourceId || !pipelinePreviewFilename) {
      setPipelineError(t("crawler.pipeline.error.preview_required"));
      return;
    }
    setPreviewLoading(true);
    setPreviewResult(null);
    setPipelineError(null);
    try {
      const data = await previewMdPipeline(
        selectedPipelineName || undefined,
        pipelinePreviewSourceId,
        pipelinePreviewFilename,
        {
          name: pipelineData.name || selectedPipelineName || "preview",
          steps: pipelineData.steps || [],
        },
      );
      setPreviewResult(data);
    } catch (e) {
      setPipelineError(e.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCreatePipeline = () => {
    setNewPipelineName("");
    setShowCreatePipelineModal(true);
  };

  const handleConfirmCreatePipeline = async () => {
    const name = (newPipelineName || "").trim().replace(/\.json$/i, "");
    if (!name) {
      setPipelineError(t("crawler.pipeline.error.name_required"));
      return;
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
      setPipelineError(t("crawler.pipeline.error.name_invalid"));
      return;
    }
    setPipelineError(null);
    setShowCreatePipelineModal(false);
    setSelectedPipelineName(name);
    setPipelineData({ name, steps: [] });
    await saveMdPipeline(name, { name, steps: [] }).catch((e) =>
      setPipelineError(e.message),
    );
    await loadMdPipelinesList();
  };

  const handleDeletePipelineClick = () => {
    setShowDeletePipelineConfirm(true);
  };

  const handleConfirmDeletePipeline = async () => {
    const nameToDelete = selectedPipelineName;
    if (!nameToDelete) return;
    setPipelineError(null);
    try {
      await deleteMdPipeline(nameToDelete);
      setShowDeletePipelineConfirm(false);
      const list = await loadMdPipelinesList();
      const next = list.filter((n) => n !== nameToDelete);
      const nextName = next.length > 0 ? next[0] : "";
      setSelectedPipelineName(nextName);
      if (nextName) {
        await loadMdPipelineBody(nextName);
      } else {
        setPipelineData({ name: "", steps: [] });
      }
    } catch (e) {
      setPipelineError(e.message);
    }
  };

  useEffect(() => {
    if (activeSection !== "md-pipeline") return;
    loadMdPipelinesList();
    if (!pipelinePreviewSources.length) loadPipelinePreviewSources();
  }, [activeSection]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (activeSection !== "md-pipeline" || !selectedPipelineName) return;
    loadMdPipelineBody(selectedPipelineName);
  }, [activeSection, selectedPipelineName]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (activeSection !== "md-pipeline") return;
    if (pipelinePreviewSourceId) {
      loadPipelinePreviewFiles(pipelinePreviewSourceId);
    } else {
      setPipelinePreviewFiles([]);
      setPipelinePreviewFilename("");
    }
  }, [activeSection, pipelinePreviewSourceId]); // eslint-disable-line react-hooks/exhaustive-deps

  const retryPipelineLoad = async () => {
    const list = await loadMdPipelinesList();
    const name = selectedPipelineName || list[0];
    if (name) await loadMdPipelineBody(name);
  };

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
    retryPipelineLoad,
  };
}
