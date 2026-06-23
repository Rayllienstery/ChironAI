import { describe, expect, it } from 'vitest';
import { actionLabel, buildActionPayload, serviceActionTimeoutMs } from './buildActionPayload';

describe('buildActionPayload', () => {
  it('maps payload keys from field state', () => {
    expect(
      buildActionPayload(['backend_url', 'selected_model'], { backend_url: 'http://x' }),
    ).toEqual({ backend_url: 'http://x', selected_model: '' });
  });

  it('applies overrides for specific keys', () => {
    expect(
      buildActionPayload(['selected_model'], {}, { selected_model: 'llama3' }),
    ).toEqual({ selected_model: 'llama3' });
  });

  it('ignores invalid keys', () => {
    expect(buildActionPayload(['', '  '], { a: '1' })).toEqual({});
  });
});

describe('actionLabel', () => {
  it('prefers label then title then action id', () => {
    expect(actionLabel({ label: 'Stop' }, 'stop')).toBe('Stop');
    expect(actionLabel({ title: 'Refresh' }, 'refresh')).toBe('Refresh');
    expect(actionLabel(null, 'delete_model')).toBe('delete_model');
  });
});

describe('serviceActionTimeoutMs', () => {
  it('uses long timeout for service start/stop', () => {
    expect(serviceActionTimeoutMs('start_service')).toBe(30 * 60 * 1000);
    expect(serviceActionTimeoutMs('refresh')).toBe(30_000);
  });
});
