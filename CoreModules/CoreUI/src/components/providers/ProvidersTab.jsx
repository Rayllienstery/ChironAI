import { useCallback, useEffect, useMemo, useState } from 'react';

import CoreUIBadge from '../CoreUIBadge';
import CoreUIButton from '../CoreUIButton';
import CoreUIPillTabs from '../CoreUIPillTabs';
import ActionableError from '../ActionableError';
import InfoButton from '../common/InfoButton.jsx';
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
import '../../styles/components/DashboardTab.css';
import '../../styles/components/SettingsTab.css';
import '../../styles/components/LlmProxyTab.css';
import '../../styles/components/ExtensionsTab.css';
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

function kvRow(label, value, key) {
  return (
    <div className="dashboard-kv-row" key={key}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value">{value}</span>
    </div>
  );
}

function CustomProviderRow({
  provider,
  testResult,
  testing,
  onTest,
  onEdit,
  onDelete,
}) {
  const hasKeyIssue = !provider.api_key_configured;
  return (
    <article
      className={`llm-proxy-build-row providers-provider-row${hasKeyIssue ? ' llm-proxy-build-row--has-issues' : ''}`}
      data-provider-id={provider.id}
    >
      <div className="llm-proxy-build-row-header">
        <div className="llm-proxy-build-main">
          <div className="llm-proxy-build-title">
            <span
              className={`llm-proxy-build-issue-icon material-symbols-outlined${hasKeyIssue ? ' llm-proxy-build-issue-icon--on' : ''}`}
              aria-hidden="true"
            >
              {hasKeyIssue ? 'error' : 'cloud'}
            </span>
            <code title={provider.id}>{provider.display_name || provider.id}</code>
            {provider.display_name && provider.display_name !== provider.id ? (
              <span className="llm-proxy-build-display-name">{provider.id}</span>
            ) : null}
            <CoreUIBadge tone={provider.enabled ? 'success' : 'neutral'}>
              {provider.enabled ? t('providers.enabled') : t('providers.disabled')}
            </CoreUIBadge>
          </div>
          <div className="llm-proxy-build-basic-info">
            <span className="llm-proxy-build-basic-item">
              <span className="material-symbols-outlined" aria-hidden="true">link</span>
              <code>{provider.base_url}</code>
            </span>
            <span className="llm-proxy-build-basic-item">
              <span className="material-symbols-outlined" aria-hidden="true">key</span>
              {provider.api_key_configured
                ? (provider.api_key_masked || t('providers.key_configured'))
                : t('providers.key_missing')}
            </span>
            {Array.isArray(provider.manual_models) && provider.manual_models.length > 0 ? (
              <span className="llm-proxy-build-basic-item">
                <span className="material-symbols-outlined" aria-hidden="true">smart_toy</span>
                {provider.manual_models.length} {t('providers.models')}
              </span>
            ) : null}
          </div>
          {testResult ? (
            <p
              className={`providers-provider-row__test-result ${
                testResult.ok ? 'providers-provider-row__test-result--ok' : 'providers-provider-row__test-result--error'
              }`}
            >
              {testResult.ok
                ? t('providers.test_ok', { count: testResult.model_count || 0 })
                : testResult.message || t('providers.test_failed')}
            </p>
          ) : null}
        </div>
        <div className="llm-proxy-build-actions">
          <CoreUIButton
            variant="secondary"
            type="button"
            data-tour="providers-test-btn"
            disabled={testing}
            onClick={() => onTest(provider.id)}
          >
            {testing ? t('providers.testing') : t('providers.test')}
          </CoreUIButton>
          <CoreUIButton variant="secondary" type="button" onClick={() => onEdit(provider)}>
            {t('providers.edit')}
          </CoreUIButton>
          <CoreUIButton variant="secondary" type="button" onClick={() => onDelete(provider.id)}>
            {t('providers.delete')}
          </CoreUIButton>
        </div>
      </div>
    </article>
  );
}

function ProviderForm({ form, editingId, editingProvider, saving, formError, onChange, onSave, onCancel }) {
  return (
    <section className="app-default-card providers-form-card" data-tour="providers-form">
      <div className="dashboard-card-header">
        <h3>{editingId ? t('providers.edit') : t('providers.add')}</h3>
      </div>
      <div className="providers-form-grid">
        <label className="coreui-form-field">
          <span>{t('providers.form.id')}</span>
          <input
            className="coreui-select"
            value={form.id}
            disabled={Boolean(editingId)}
            onChange={(event) => onChange({ id: event.target.value })}
            placeholder="my-openai-gateway"
            autoComplete="off"
          />
        </label>
        <label className="coreui-form-field">
          <span>{t('providers.form.display_name')}</span>
          <input
            className="coreui-select"
            value={form.display_name}
            onChange={(event) => onChange({ display_name: event.target.value })}
            autoComplete="off"
          />
        </label>
        <label className="coreui-form-field providers-form-grid__wide">
          <span>{t('providers.form.base_url')}</span>
          <input
            className="coreui-select"
            value={form.base_url}
            onChange={(event) => onChange({ base_url: event.target.value })}
            placeholder="https://api.openai.com"
            autoComplete="off"
          />
        </label>
        <label className="coreui-form-field providers-form-grid__wide">
          <span>{t('providers.form.api_key')}</span>
          <input
            className="coreui-select"
            type="password"
            value={form.api_key}
            onChange={(event) => onChange({ api_key: event.target.value })}
            placeholder={editingProvider?.api_key_configured ? t('providers.form.api_key_unchanged') : ''}
            autoComplete="new-password"
          />
        </label>
        <label className="coreui-form-field">
          <span>{t('providers.form.organization')}</span>
          <input
            className="coreui-select"
            value={form.organization}
            onChange={(event) => onChange({ organization: event.target.value })}
            autoComplete="off"
          />
        </label>
        <label className="coreui-form-field providers-form-grid__wide">
          <span>{t('providers.form.manual_models')}</span>
          <textarea
            className="coreui-select providers-form-textarea"
            value={form.manual_models}
            onChange={(event) => onChange({ manual_models: event.target.value })}
            placeholder="gpt-4o-mini"
          />
        </label>
        <label className="coreui-form-field providers-form-checkbox">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(event) => onChange({ enabled: event.target.checked })}
          />
          <span>{t('providers.form.enabled')}</span>
        </label>
      </div>
      {formError ? <ActionableError error={formError} title={t('providers.form.error')} /> : null}
      <div className="dashboard-card-actions providers-form-actions">
        <CoreUIButton variant="primary" type="button" disabled={saving} onClick={onSave}>
          {saving ? t('providers.saving') : t('providers.save')}
        </CoreUIButton>
        <CoreUIButton variant="secondary" type="button" disabled={saving} onClick={onCancel}>
          {t('providers.cancel')}
        </CoreUIButton>
      </div>
    </section>
  );
}

export default function ProvidersTab({ onNavigate }) {
  const [subTab, setSubTab] = useState('custom');
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

  const subTabs = useMemo(
    () => [
      { id: 'custom', label: t('providers.subtab.custom') },
      { id: 'extensions', label: t('providers.subtab.extensions') },
    ],
    [],
  );

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
    setSubTab('custom');
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
    setSubTab('custom');
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const handleFormChange = (patch) => {
    setForm((prev) => ({ ...prev, ...patch }));
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
      <div className="settings-tab settings-tab--fullwidth llm-proxy-tab providers-tab tab-view">
        <p className="settings-intro">{t('providers.loading')}</p>
      </div>
    );
  }

  return (
    <div className="settings-tab settings-tab--fullwidth llm-proxy-tab providers-tab tab-view">
      <div className="llm-proxy-header" data-tour="providers-header">
        <div className="llm-proxy-header-row llm-proxy-builds-card-header">
          <h2>{t('nav.providers')}</h2>
          <InfoButton helpRef="providers" label={t('nav.providers')} />
        </div>
        <CoreUIPillTabs
          tabs={subTabs}
          value={subTab}
          onChange={setSubTab}
          ariaLabel={t('nav.providers')}
        />
      </div>

      <p className="settings-intro">{t('providers.intro')}</p>

      {error ? (
        <ActionableError error={error} title={t('providers.load_error')} onRetry={loadData} />
      ) : null}

      <div className="settings-form">
        <section className="app-default-card llm-proxy-status-card" aria-labelledby="providers-overview-heading">
          <div className="dashboard-card-header">
            <h3 id="providers-overview-heading">{t('providers.overview_title')}</h3>
            <div className="dashboard-card-actions">
              <CoreUIButton variant="primary" type="button" onClick={loadData}>
                {t('providers.refresh')}
              </CoreUIButton>
            </div>
          </div>
          {kvRow(t('providers.overview_custom'), customProviders.length, 'custom-count')}
          {kvRow(t('providers.overview_extensions'), extensionProviders.length, 'ext-count')}
        </section>

        {subTab === 'custom' ? (
          <>
            <div className="dashboard-card-actions llm-proxy-section-gap">
              <CoreUIButton
                variant="primary"
                type="button"
                data-tour="providers-add-btn"
                onClick={openCreateForm}
                disabled={formOpen && !editingId}
              >
                {t('providers.add')}
              </CoreUIButton>
            </div>

            {formOpen ? (
              <ProviderForm
                form={form}
                editingId={editingId}
                editingProvider={editingProvider}
                saving={saving}
                formError={formError}
                onChange={handleFormChange}
                onSave={handleSave}
                onCancel={closeForm}
              />
            ) : null}

            <section className="app-default-card" data-tour="providers-custom-list">
              <div className="dashboard-card-header llm-proxy-builds-card-header">
                <h3>{t('providers.custom_title')}</h3>
                <CoreUIBadge tone="info">{customProviders.length}</CoreUIBadge>
              </div>
              {customProviders.length === 0 ? (
                <p className="dashboard-card-muted">{t('providers.empty_description')}</p>
              ) : (
                <div className="llm-proxy-builds-list" role="list" aria-label={t('providers.custom_title')}>
                  {customProviders.map((provider) => (
                    <CustomProviderRow
                      key={provider.id}
                      provider={provider}
                      testResult={testResults[provider.id]}
                      testing={testingId === provider.id}
                      onTest={handleTest}
                      onEdit={openEditForm}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              )}
            </section>
          </>
        ) : null}

        {subTab === 'extensions' ? (
          <section className="app-default-card extensions-view" data-tour="providers-extensions">
            <div className="extensions-view__header">
              <h3>{t('providers.extensions_title')}</h3>
              <div className="extensions-view__header-badges">
                <CoreUIBadge tone="info">{extensionProviders.length}</CoreUIBadge>
                {onNavigate ? (
                  <CoreUIButton variant="secondary" type="button" onClick={() => onNavigate('extensions')}>
                    {t('providers.open_extensions')}
                  </CoreUIButton>
                ) : null}
              </div>
            </div>
            <p className="settings-form-hint">{t('providers.extensions_hint')}</p>
            <div className="extensions-cards">
              {extensionProviders.map((row) => (
                <article
                  key={row.provider_id || row.id}
                  className="coreui-card-shell coreui-p-md extensions-card extensions-card--horizontal provider-card"
                >
                  <div className="extensions-card__main">
                    <div className="extensions-card__identity">
                      <span className="material-symbols-outlined extensions-card__icon" aria-hidden="true">
                        hub
                      </span>
                      <div className="extensions-card__copy">
                        <h4>{row.title || row.provider_id || row.id}</h4>
                        <p>{row.description || row.provider_id || row.id}</p>
                      </div>
                    </div>
                    <div className="extensions-card__meta-row" aria-label={t('providers.extensions_title')}>
                      <CoreUIBadge tone="neutral">{row.provider_id || row.id}</CoreUIBadge>
                      {row.extension_id ? <CoreUIBadge tone="neutral">{row.extension_id}</CoreUIBadge> : null}
                      {Array.isArray(row.models) && row.models.length > 0 ? (
                        <CoreUIBadge tone="info">
                          {row.models.length} {t('providers.models')}
                        </CoreUIBadge>
                      ) : null}
                    </div>
                  </div>
                </article>
              ))}
              {extensionProviders.length === 0 ? (
                <div className="extensions-empty">{t('providers.extensions_empty_description')}</div>
              ) : null}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
