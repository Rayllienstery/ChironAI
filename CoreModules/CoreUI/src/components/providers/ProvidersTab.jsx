import { useCallback, useEffect, useMemo, useState } from 'react';

import CoreUIBadge from '../CoreUIBadge';
import CoreUIButton from '../CoreUIButton';
import ActionableError from '../ActionableError';
import EmptyState from '../EmptyState';
import { resolveProvidersTourSteps } from '../onboarding/contextualTours.js';
import { useContextualTour } from '../onboarding/useContextualTour.js';
import {
  createCustomProvider,
  deleteCustomProvider,
  listCustomProviders,
  testCustomProvider,
  updateCustomProvider,
} from '../../services/providers.js';
import { getExtensionProviders } from '../../services/api.js';
import { t } from '../../services/i18n';
import '../../styles/components/ProvidersTab.css';

const EMPTY_FORM = {
  id: '',
  display_name: '',
  base_url: '',
  api_key: '',
  organization: '',
  manual_models: '',
  enabled: true,
};

function parseManualModels(text) {
  return String(text || '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatManualModels(models) {
  return Array.isArray(models) ? models.join('\n') : '';
}

export default function ProvidersTab({ onNavigate }) {
  const [customProviders, setCustomProviders] = useState([]);
  const [extensionProviders, setExtensionProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [testResults, setTestResults] = useState({});

  const providersTourSteps = useMemo(() => resolveProvidersTourSteps(), []);
  useContextualTour('providers', providersTourSteps, !loading);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [customPayload, extensionPayload] = await Promise.all([
        listCustomProviders(),
        getExtensionProviders().catch(() => ({ providers: [] })),
      ]);
      setCustomProviders(Array.isArray(customPayload?.providers) ? customPayload.providers : []);
      const rows = extensionPayload?.providers ?? extensionPayload?.rows ?? [];
      setExtensionProviders(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const editingProvider = useMemo(
    () => customProviders.find((row) => row.id === editingId) || null,
    [customProviders, editingId],
  );

  const openCreateForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setFormOpen(true);
  };

  const openEditForm = (provider) => {
    setEditingId(provider.id);
    setForm({
      id: provider.id,
      display_name: provider.display_name || provider.id,
      base_url: provider.base_url || '',
      api_key: '',
      organization: provider.organization || '',
      manual_models: formatManualModels(provider.manual_models),
      enabled: provider.enabled !== false,
    });
    setFormError(null);
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setFormError(null);
    const payload = {
      id: form.id.trim(),
      display_name: form.display_name.trim() || form.id.trim(),
      base_url: form.base_url.trim(),
      organization: form.organization.trim(),
      manual_models: parseManualModels(form.manual_models),
      enabled: Boolean(form.enabled),
    };
    if (form.api_key.trim()) {
      payload.api_key = form.api_key.trim();
    }
    try {
      if (editingId) {
        await updateCustomProvider(editingId, payload);
      } else {
        if (!payload.api_key) {
          throw new Error(t('providers.form.api_key_required'));
        }
        await createCustomProvider(payload);
      }
      closeForm();
      await loadData();
    } catch (err) {
      setFormError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (providerId) => {
    if (!window.confirm(t('providers.confirm_delete'))) return;
    try {
      await deleteCustomProvider(providerId);
      await loadData();
    } catch (err) {
      setError(err);
    }
  };

  const handleTest = async (providerId) => {
    setTestingId(providerId);
    try {
      const { data } = await testCustomProvider(providerId);
      setTestResults((prev) => ({ ...prev, [providerId]: data }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [providerId]: { ok: false, status: 'error', message: String(err?.message || err) },
      }));
    } finally {
      setTestingId(null);
    }
  };

  if (loading) {
    return (
      <div className="providers-tab app-main">
        <p>{t('providers.loading')}</p>
      </div>
    );
  }

  return (
    <div className="providers-tab app-main">
      <header className="providers-tab__header" data-tour="providers-header">
        <h1>{t('nav.providers')}</h1>
        <p>{t('providers.intro')}</p>
      </header>

      {error ? (
        <ActionableError error={error} title={t('providers.load_error')} onRetry={loadData} />
      ) : null}

      <section className="providers-tab__section" data-tour="providers-custom-list">
        <div className="providers-tab__section-header">
          <h2>{t('providers.custom_title')}</h2>
          <CoreUIButton
            variant="primary"
            type="button"
            data-tour="providers-add-btn"
            onClick={openCreateForm}
          >
            {t('providers.add')}
          </CoreUIButton>
        </div>

        {formOpen ? (
          <div className="providers-tab__form" data-tour="providers-form">
            <label>
              {t('providers.form.id')}
              <input
                value={form.id}
                disabled={Boolean(editingId)}
                onChange={(event) => setForm((prev) => ({ ...prev, id: event.target.value }))}
                placeholder="my-openai-gateway"
                autoComplete="off"
              />
            </label>
            <label>
              {t('providers.form.display_name')}
              <input
                value={form.display_name}
                onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))}
                autoComplete="off"
              />
            </label>
            <label>
              {t('providers.form.base_url')}
              <input
                value={form.base_url}
                onChange={(event) => setForm((prev) => ({ ...prev, base_url: event.target.value }))}
                placeholder="https://api.openai.com"
                autoComplete="off"
              />
            </label>
            <label>
              {t('providers.form.api_key')}
              <input
                type="password"
                value={form.api_key}
                onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))}
                placeholder={editingProvider?.api_key_configured ? t('providers.form.api_key_unchanged') : ''}
                autoComplete="new-password"
              />
            </label>
            <label>
              {t('providers.form.organization')}
              <input
                value={form.organization}
                onChange={(event) => setForm((prev) => ({ ...prev, organization: event.target.value }))}
                autoComplete="off"
              />
            </label>
            <label>
              {t('providers.form.manual_models')}
              <textarea
                value={form.manual_models}
                onChange={(event) => setForm((prev) => ({ ...prev, manual_models: event.target.value }))}
                placeholder="gpt-4o-mini"
              />
            </label>
            <label>
              <span>{t('providers.form.enabled')}</span>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setForm((prev) => ({ ...prev, enabled: event.target.checked }))}
              />
            </label>
            {formError ? <ActionableError error={formError} title={t('providers.form.error')} /> : null}
            <div className="providers-tab__form-actions">
              <CoreUIButton variant="primary" type="button" disabled={saving} onClick={handleSave}>
                {saving ? t('providers.saving') : t('providers.save')}
              </CoreUIButton>
              <CoreUIButton variant="secondary" type="button" disabled={saving} onClick={closeForm}>
                {t('providers.cancel')}
              </CoreUIButton>
            </div>
          </div>
        ) : null}

        {customProviders.length === 0 ? (
          <EmptyState>
            <strong>{t('providers.empty_title')}</strong>
            <p>{t('providers.empty_description')}</p>
          </EmptyState>
        ) : (
          <div className="providers-tab__table-wrap">
            <table className="providers-tab__table">
              <thead>
                <tr>
                  <th>{t('providers.table.id')}</th>
                  <th>{t('providers.table.base_url')}</th>
                  <th>{t('providers.table.status')}</th>
                  <th>{t('providers.table.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {customProviders.map((provider) => {
                  const testResult = testResults[provider.id];
                  return (
                    <tr key={provider.id}>
                      <td>
                        <strong>{provider.display_name || provider.id}</strong>
                        <div style={{ fontSize: '0.75rem', opacity: 0.8 }}>{provider.id}</div>
                      </td>
                      <td>{provider.base_url}</td>
                      <td>
                        <CoreUIBadge tone={provider.enabled ? 'success' : 'neutral'}>
                          {provider.enabled ? t('providers.enabled') : t('providers.disabled')}
                        </CoreUIBadge>
                        {provider.api_key_configured ? (
                          <div style={{ fontSize: '0.75rem', marginTop: 4 }}>
                            {provider.api_key_masked || t('providers.key_configured')}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.75rem', marginTop: 4, color: 'var(--md-sys-color-error)' }}>
                            {t('providers.key_missing')}
                          </div>
                        )}
                        {testResult ? (
                          <div
                            className={`providers-tab__test-result ${
                              testResult.ok ? 'providers-tab__test-result--ok' : 'providers-tab__test-result--error'
                            }`}
                          >
                            {testResult.ok
                              ? t('providers.test_ok', { count: testResult.model_count || 0 })
                              : testResult.message || t('providers.test_failed')}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <div className="providers-tab__actions">
                          <CoreUIButton
                            variant="secondary"
                            type="button"
                            disabled={testingId === provider.id}
                            onClick={() => handleTest(provider.id)}
                          >
                            {testingId === provider.id ? t('providers.testing') : t('providers.test')}
                          </CoreUIButton>
                          <CoreUIButton variant="secondary" type="button" onClick={() => openEditForm(provider)}>
                            {t('providers.edit')}
                          </CoreUIButton>
                          <CoreUIButton variant="secondary" type="button" onClick={() => handleDelete(provider.id)}>
                            {t('providers.delete')}
                          </CoreUIButton>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="providers-tab__section" data-tour="providers-extensions">
        <div className="providers-tab__section-header">
          <h2>{t('providers.extensions_title')}</h2>
          {onNavigate ? (
            <CoreUIButton variant="secondary" type="button" onClick={() => onNavigate('extensions')}>
              {t('providers.open_extensions')}
            </CoreUIButton>
          ) : null}
        </div>
        <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--md-sys-color-on-surface-variant)' }}>
          {t('providers.extensions_hint')}
        </p>
        {extensionProviders.length === 0 ? (
          <EmptyState>
            <strong>{t('providers.extensions_empty_title')}</strong>
            <p>{t('providers.extensions_empty_description')}</p>
          </EmptyState>
        ) : (
          <div className="providers-tab__extension-list">
            {extensionProviders.map((row) => (
              <article key={row.provider_id || row.id} className="providers-tab__extension-card">
                <h3>{row.title || row.provider_id || row.id}</h3>
                <p>
                  {row.provider_id || row.id}
                  {Array.isArray(row.models) && row.models.length > 0
                    ? ` · ${row.models.length} ${t('providers.models')}`
                    : ''}
                </p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
