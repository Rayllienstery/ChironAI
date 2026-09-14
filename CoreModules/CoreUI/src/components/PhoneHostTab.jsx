import { useCallback, useEffect, useState } from 'react';
import { getPhoneHostScripts, setPhoneHostScriptEnabled } from '../services/api';
import { t } from '../services/i18n';
import ActionableError from './ActionableError';
import Card from './Card';
import EmptyState from './EmptyState';
import '../styles/components/PhoneHostTab.css';

const OWUI_WAKE_FACTS = [
  { labelKey: 'phone_host.owui.mac', value: '74:56:3C:36:A3:76' },
  { labelKey: 'phone_host.owui.ip', value: '192.168.50.115' },
  { labelKey: 'phone_host.owui.url', value: 'http://192.168.50.115:3000' },
  { labelKey: 'phone_host.owui.door', value: 'http://192.168.50.1:9377/' },
];

function scriptTitle(id, fallback) {
  const key = `phone_host.script.${id}.title`;
  const label = t(key);
  return label === key ? fallback : label;
}

function scriptDescription(id, fallback) {
  const key = `phone_host.script.${id}.description`;
  const label = t(key);
  return label === key ? fallback : label;
}

function errorTitle(error, kind) {
  if (error?.status === 404) {
    return t('phone_host.stale_backend');
  }
  return kind === 'save' ? t('phone_host.save_error') : t('phone_host.load_error');
}

export default function PhoneHostTab() {
  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [errorKind, setErrorKind] = useState('load');
  const [pendingId, setPendingId] = useState(null);

  const loadScripts = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await getPhoneHostScripts();
      setScripts(Array.isArray(data?.scripts) ? data.scripts : []);
    } catch (err) {
      setScripts([]);
      setErrorKind('load');
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadScripts();
  }, [loadScripts]);

  const handleToggle = async (script, enabled) => {
    const id = script.id;
    setPendingId(id);
    setScripts((current) => current.map((row) => (row.id === id ? { ...row, enabled } : row)));
    try {
      const data = await setPhoneHostScriptEnabled(id, enabled);
      if (Array.isArray(data?.scripts)) {
        setScripts(data.scripts);
      }
      setError(null);
    } catch (err) {
      setScripts((current) => current.map((row) => (row.id === id ? { ...row, enabled: script.enabled } : row)));
      setErrorKind('save');
      setError(err);
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="phone-host-tab tab-view">
      <header className="phone-host-header">
        <h1 className="phone-host-title">{t('phone_host.title')}</h1>
        <p className="phone-host-lead">{t('phone_host.lead')}</p>
      </header>

      {loading && <p className="phone-host-status">{t('phone_host.loading')}</p>}
      {error && !loading && (
        <ActionableError
          error={error}
          title={errorTitle(error, errorKind)}
          onRetry={loadScripts}
        />
      )}
      {!loading && !error && scripts.length === 0 && (
        <EmptyState>{t('phone_host.empty')}</EmptyState>
      )}

      <Card className="phone-host-card">
        <div className="phone-host-card-copy">
          <h2 className="phone-host-card-title">{t('phone_host.owui.title')}</h2>
          <p className="phone-host-card-description">{t('phone_host.owui.lead')}</p>
          <ol className="phone-host-steps">
            <li>{t('phone_host.owui.step_sleep')}</li>
            <li>{t('phone_host.owui.step_door')}</li>
            <li>{t('phone_host.owui.step_shortcut')}</li>
          </ol>
          <dl className="phone-host-facts">
            {OWUI_WAKE_FACTS.map((fact) => (
              <div key={fact.labelKey} className="phone-host-fact">
                <dt>{t(fact.labelKey)}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </Card>

      <div className="phone-host-list">
        {scripts.map((script) => {
          const enabled = Boolean(script.enabled);
          const switchId = `phone-host-script-${script.id}`;
          return (
            <Card key={script.id} className="phone-host-card">
              <div className="phone-host-card-row">
                <div className="phone-host-card-copy">
                  <h2 className="phone-host-card-title">
                    {scriptTitle(script.id, script.title)}
                  </h2>
                  <p className="phone-host-card-description">
                    {scriptDescription(script.id, script.description)}
                  </p>
                  <p className="phone-host-card-file">
                    {script.path}
                    {script.wrapper ? ` · ${script.wrapper}` : ''}
                    {script.exists ? '' : ` · ${t('phone_host.file_missing')}`}
                  </p>
                </div>
                <label className="coreui-switch" htmlFor={switchId}>
                  <input
                    id={switchId}
                    type="checkbox"
                    checked={enabled}
                    disabled={pendingId === script.id}
                    onChange={(event) => handleToggle(script, event.target.checked)}
                    aria-label={scriptTitle(script.id, script.title)}
                  />
                  <span aria-hidden="true" />
                </label>
              </div>
              <p className="phone-host-card-state">
                {enabled ? t('phone_host.enabled') : t('phone_host.disabled')}
              </p>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
