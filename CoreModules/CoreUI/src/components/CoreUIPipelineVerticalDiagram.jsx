import { useMemo } from 'react';
import { computePipelineActive } from './PipelineCiDiagram';
import CoreUIPipelinePreview from './CoreUIPipelinePreview';

function getVerticalSteps(data) {
  const defs = data?.pipeline_definition?.proxy?.steps;
  if (!Array.isArray(defs)) return [];
  return defs
    .filter((s) => s && typeof s === 'object' && s.id)
    .map((s) => ({
      id: String(s.id),
      icon: String(s.icon || 'settings'),
      label: String(s.title || s.label || s.id),
      description: String(s.description || ''),
    }));
}

function CoreUIPipelineVerticalDiagram({ data }) {
  const activeMap = useMemo(() => (data ? computePipelineActive(data) : null), [data]);
  const steps = useMemo(() => {
    const rawSteps = getVerticalSteps(data);
    if (!activeMap) return rawSteps;
    return rawSteps.map(s => ({
      ...s,
      active: Boolean(activeMap[s.id])
    }));
  }, [data, activeMap]);

  if (!activeMap || steps.length < 1) return null;

  return <CoreUIPipelinePreview steps={steps} />;
}

export default CoreUIPipelineVerticalDiagram;
