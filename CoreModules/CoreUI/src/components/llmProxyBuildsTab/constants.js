export const SECTION_TABS = [
  { id: 'builds', label: 'Builds' },
  { id: 'autocomplete', label: 'Autocomplete' },
];

export const WIZARD_STEPS = [
  { id: 'basic', label: 'Basic Info', icon: 'info' },
  { id: 'rag', label: 'RAG', icon: 'search' },
  { id: 'privacy', label: 'Privacy', icon: 'lock' },
  { id: 'agent', label: 'Agent Proxy Mode', icon: 'terminal' },
  { id: 'parameters', label: 'Parameters', icon: 'tune' },
  { id: 'web', label: 'Web Knowledge', icon: 'language' },
];

export const PARAMETER_PREFABS = [
  {
    id: 'light',
    label: 'Light',
    icon: 'bolt',
    values: { num_ctx: 32768, num_predict: 4096, max_agent_steps: 10 },
    description: 'Quick fixes and single-file edits. 10 steps covers simple tool-using agents (read → edit → verify) without runaway loops.',
  },
  {
    id: 'medium',
    label: 'Medium',
    icon: 'tune',
    values: { num_ctx: 65536, num_predict: 8192, max_agent_steps: 25 },
    description: 'Feature implementation and unit tests. 25 steps handles a typical plan → implement → test → fix cycle on a single module.',
  },
  {
    id: 'high',
    label: 'High',
    icon: 'rocket_launch',
    values: { num_ctx: 131072, num_predict: 16384, max_agent_steps: 60 },
    description: 'Multi-file refactors and complex features. Research benchmarks place real agentic coding tasks at 40–80 steps; 60 is the reliable midpoint.',
  },
  {
    id: 'extreme',
    label: 'Extreme',
    icon: 'warning',
    values: { num_ctx: 202752, num_predict: 32768, max_agent_steps: 128 },
    description: '200K context for full-codebase sessions. 128 steps supports long-horizon work (migrations, multi-module rewrites). Beyond this, use durable project memory files instead.',
  },
];

export const CUSTOM_PARAMETER_PREFAB_NOTE = {
  label: 'Custom values',
  values: null,
  description: 'Current fields do not match a prefab. Manual values will be saved as-is, and num_predict will reserve output room inside num_ctx.',
};

