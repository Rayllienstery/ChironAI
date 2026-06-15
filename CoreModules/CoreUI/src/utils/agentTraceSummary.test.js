import { describe, expect, it } from 'vitest';
import { summarizeAgentTraceMeta } from '../utils/agentTraceSummary.js';

describe('summarizeAgentTraceMeta', () => {
  it('returns empty marker for missing meta', () => {
    expect(summarizeAgentTraceMeta(null)).toEqual({ empty: true });
  });

  it('counts model_call steps', () => {
    const summary = summarizeAgentTraceMeta({
      steps: [{ kind: 'model_call', step: 1, ok: true }],
      step_count: 1,
      elapsed_ms: 42,
    });
    expect(summary.stepCount).toBe(1);
    expect(summary.durationMs).toBe(42);
  });
});
