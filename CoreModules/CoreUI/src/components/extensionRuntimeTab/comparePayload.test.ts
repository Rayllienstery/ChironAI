import { describe, expect, it } from 'vitest';
import {
  extensionTabPayloadsEqual,
  fieldStatesEqual,
} from './comparePayload';

describe('extensionTabPayloadsEqual', () => {
  const base = {
    load_state: { status: 'ready', cached_at: '2026-01-01T00:00:00Z', phases: {} },
    content: { type: 'service_panel', status: 'running', fields: [{ key: 'backend_url', value: 'http://x' }] },
    schema: {
      pages: [{
        sections: [{
          components: [{ type: 'input', key: 'backend_url', value: 'http://x' }],
        }],
      }],
    },
  };

  it('returns true for structurally equal payloads', () => {
    expect(extensionTabPayloadsEqual(base, { ...base })).toBe(true);
  });

  it('returns false when load_state status changes', () => {
    expect(
      extensionTabPayloadsEqual(base, {
        ...base,
        load_state: { ...base.load_state, status: 'refreshing' },
      }),
    ).toBe(false);
  });

  it('returns false when schema component value changes', () => {
    const next = {
      ...base,
      schema: {
        pages: [{
          sections: [{
            components: [{ type: 'input', key: 'backend_url', value: 'http://y' }],
          }],
        }],
      },
    };
    expect(extensionTabPayloadsEqual(base, next)).toBe(false);
  });

  it('handles null prev', () => {
    expect(extensionTabPayloadsEqual(null, base)).toBe(false);
  });
});

describe('fieldStatesEqual', () => {
  it('compares shallow field maps', () => {
    expect(fieldStatesEqual({ a: '1' }, { a: '1' })).toBe(true);
    expect(fieldStatesEqual({ a: '1' }, { a: '2' })).toBe(false);
    expect(fieldStatesEqual({ a: '1' }, { a: '1', b: '2' })).toBe(false);
  });
});
