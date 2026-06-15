import { describe, expect, it } from 'vitest';
import { traceModelFields } from '../utils/proxyTraceModel.js';

describe('traceModelFields', () => {
  it('returns N/A when trace is null', () => {
    expect(traceModelFields(null)).toEqual({
      headerShort: 'N/A',
      provider: null,
      requested: null,
      actual: null,
    });
  });

  it('prefers provider model for header', () => {
    const result = traceModelFields({
      request: { requested_model: 'req', actual_model: 'act' },
      provider: { model: 'prov' },
    });
    expect(result.headerShort).toBe('prov');
    expect(result.provider).toBe('prov');
  });
});
