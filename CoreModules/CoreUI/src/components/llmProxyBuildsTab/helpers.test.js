import { describe, expect, it } from 'vitest';
import {
  buildToDraft,
  draftToPayload,
  emptyDraft,
  getMatchingParameterPrefab,
  mergeBuildDraftIntoPipelinePreview,
} from './helpers';
import { PARAMETER_PREFABS } from './constants';

describe('llmProxyBuildsTab helpers', () => {
  describe('emptyDraft', () => {
    it('returns a build draft with rag_fusion defaults', () => {
      const draft = emptyDraft();
      expect(draft.backend).toBe('rag_fusion');
      expect(draft.rag_enabled).toBe(true);
      expect(draft.sse_streaming).toBe(true);
    });
  });

  describe('getMatchingParameterPrefab', () => {
    it('matches a prefab when draft fields align', () => {
      const prefab = PARAMETER_PREFABS[1];
      const draft = {
        ...emptyDraft(),
        num_ctx: String(prefab.values.num_ctx),
        num_predict: String(prefab.values.num_predict),
        max_agent_steps: String(prefab.values.max_agent_steps),
      };
      expect(getMatchingParameterPrefab(draft)).toEqual(prefab);
    });

    it('returns null when values do not match any prefab', () => {
      expect(getMatchingParameterPrefab({ num_ctx: '1', num_predict: '2', max_agent_steps: '3' })).toBeNull();
    });
  });

  describe('buildToDraft', () => {
    it('maps build record fields into draft strings', () => {
      const draft = buildToDraft({
        id: 'dev-build',
        display_name: 'Dev',
        provider_id: 'ollama',
        model: 'llama3',
        rag_enabled: false,
        rag_collection: 'ios-docs',
        temperature: 0.7,
      });
      expect(draft.id).toBe('dev-build');
      expect(draft.display_name).toBe('Dev');
      expect(draft.provider_id).toBe('ollama');
      expect(draft.model).toBe('llama3');
      expect(draft.rag_enabled).toBe(false);
      expect(draft.rag_collection).toBe('ios-docs');
      expect(draft.temperature).toBe('0.7');
    });

    it('falls back to ollama_model when model is missing', () => {
      const draft = buildToDraft({ id: 'legacy', ollama_model: 'mistral' });
      expect(draft.model).toBe('mistral');
    });
  });

  describe('draftToPayload', () => {
    it('normalizes draft into API payload', () => {
      const payload = draftToPayload({
        ...emptyDraft(),
        id: '  my-build ',
        display_name: '',
        provider_id: 'ollama',
        model: 'llama3',
        temperature: '0.5',
        num_ctx: '65536',
        max_agent_steps: '25',
      });
      expect(payload.id).toBe('my-build');
      expect(payload.display_name).toBe('my-build');
      expect(payload.temperature).toBe(0.5);
      expect(payload.num_ctx).toBe(65536);
      expect(payload.max_agent_steps).toBe(25);
      expect(payload.ide_mode).toBe(false);
    });

    it('omits empty numeric fields from payload', () => {
      const payload = draftToPayload(emptyDraft());
      expect(payload.temperature).toBeUndefined();
      expect(payload.num_ctx).toBeUndefined();
    });

    it('preserves rag_collection in payload', () => {
      const payload = draftToPayload({ ...emptyDraft(), id: 'rag-build', rag_collection: 'ios-docs' });
      expect(payload.rag_collection).toBe('ios-docs');
    });

    it('trims rag_collection in payload', () => {
      const payload = draftToPayload({ ...emptyDraft(), id: 'rag-build', rag_collection: '  ios-docs  ' });
      expect(payload.rag_collection).toBe('ios-docs');
    });
  });

  describe('mergeBuildDraftIntoPipelinePreview', () => {
    it('disables web pipeline steps when web is off', () => {
      const snapshot = {
        env: { ddg_news: true, fetch_page: true, wikipedia: true },
        rag_collection_configured: true,
        fetch_web_knowledge: true,
        web_interaction_enabled: true,
      };
      const merged = mergeBuildDraftIntoPipelinePreview(snapshot, null, null, {
        ...emptyDraft(),
        web_enabled: false,
        rag_enabled: true,
        rag_collection: 'docs',
      });
      expect(merged.env.ddg_news).toBe(false);
      expect(merged.env.fetch_page).toBe(false);
      expect(merged.env.wikipedia).toBe(false);
      expect(merged.fetch_web_knowledge).toBe(false);
      expect(merged.web_interaction_enabled).toBe(false);
    });

    it('returns null when snapshot or draft is missing', () => {
      expect(mergeBuildDraftIntoPipelinePreview(null, null, null, emptyDraft())).toBeNull();
      expect(mergeBuildDraftIntoPipelinePreview({}, null, null, null)).toBeNull();
    });
  });
});
