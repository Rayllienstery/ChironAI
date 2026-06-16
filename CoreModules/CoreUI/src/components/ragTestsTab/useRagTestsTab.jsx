import { useRagTestsActions } from './useRagTestsActions.jsx';
import { useRagTestsCore } from './useRagTestsCore.jsx';

export function useRagTestsTab(props) {
  const core = useRagTestsCore(props);
  const actions = useRagTestsActions(core, props);
  return { ...core, ...actions };
}
