/** First-run product tour — custom M3 engine (no @reactour/tour dependency). */

export const FIRST_RUN_TOUR_STEPS = [
  {
    id: 'welcome',
    title: 'Welcome to ChironAI',
    body: 'This short tour highlights the main areas: dashboard health, LLM Proxy builds, in-app Help, and Settings.',
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    body: 'Check service health, GPU metrics, and quick links to start the stack or open logs.',
    target: '[data-tour="dashboard"]',
  },
  {
    id: 'builds',
    title: 'LLM Proxy Builds',
    body: 'Create named builds that clients reference as OpenAI `model` ids — each with its own provider, RAG collection, and parameters.',
    target: '[data-tour="llm-proxy"]',
  },
  {
    id: 'help',
    title: 'Help knowledge base',
    body: 'Browse operator guides for builds, RAG, providers, extensions, and troubleshooting. Field-level (i) buttons open the same articles in context.',
    target: '[data-tour="help"]',
  },
  {
    id: 'settings',
    title: 'Settings',
    body: 'Tune server port, theme, developer mode, and proxy defaults. You can restart this tour from Settings later.',
    target: '[data-tour="settings"]',
  },
];
