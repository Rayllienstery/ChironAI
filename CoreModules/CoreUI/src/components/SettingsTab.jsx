import { useState, useEffect } from 'react';
import { getSettings, updateSettings } from '../services/api';
import { getLocale, setLocale, SUPPORTED_LOCALES, t } from '../services/i18n';
import CoreUIButton from './CoreUIButton';
import { restartFirstRunTour } from './onboarding/OnboardingProvider.jsx';
import '../styles/components/SettingsTab.css';
import '../styles/components/DashboardTab.css';

const ACCENT_COLORS = [
  { id: 'purple', light: '#6750A4', dark: '#D0BCFF' },
  { id: 'blue', light: '#005AC1', dark: '#ABC7FF' },
  { id: 'dark-green', light: '#2E7D32', dark: '#81C784' },
  { id: 'cyan', light: '#006780', dark: '#5DD4FC' },
  { id: 'teal', light: '#006A60', dark: '#82D5C8' },
  { id: 'orange', light: '#8B5000', dark: '#FFB873' },
  { id: 'red', light: '#BA1A1A', dark: '#FFB4AB' },
  { id: 'pink', light: '#984061', dark: '#FFB0C8' },
  { id: 'indigo', light: '#3D5AA9', dark: '#B8C4FF' },
  { id: 'amber', light: '#7D5700', dark: '#F2C029' },
  { id: 'slate', light: '#4A6572', dark: '#B0C9D6' },
  { id: 'lime', light: '#4A6B00', dark: '#C6E063' },
  { id: 'violet', light: '#5B3F94', dark: '#CBBEFF' },
  { id: 'coral', light: '#9E4242', dark: '#FFB3B0' },
];

const SERVICE_STATUS_POLL_DEFAULT = 5;
const SERVICE_STATUS_POLL_MIN = 2;
const SERVICE_STATUS_POLL_MAX = 300;
const SERVER_PORT_MIN = 1;
const SERVER_PORT_MAX = 65535;

function clampServiceStatusPollSec(raw) {
  const n = parseInt(String(raw ?? ''), 10);
  if (Number.isNaN(n)) return SERVICE_STATUS_POLL_DEFAULT;
  return Math.min(SERVICE_STATUS_POLL_MAX, Math.max(SERVICE_STATUS_POLL_MIN, n));
}

import { parseDeveloperMode } from '../utils/developerMode';

function SettingsTab({
  themeMode,
  lightAccent,
  darkAccent,
  locale,
  developerMode,
  onThemeChange,
  onLocaleChange,
  onDeveloperModeChange,
  onAppSettingsSaved,
}) {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [localThemeMode, setLocalThemeMode] = useState(themeMode || 'system');
  const [localLightAccent, setLocalLightAccent] = useState(lightAccent || 'purple');
  const [localDarkAccent, setLocalDarkAccent] = useState(darkAccent || 'cyan');
  const [localLocale, setLocalLocale] = useState(locale || getLocale());
  const [localDeveloperMode, setLocalDeveloperMode] = useState(Boolean(developerMode));

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    if (themeMode) setLocalThemeMode(themeMode);
    if (lightAccent) setLocalLightAccent(lightAccent);
    if (darkAccent) setLocalDarkAccent(darkAccent);
    if (locale) setLocalLocale(locale);
  }, [themeMode, lightAccent, darkAccent, locale]);

  useEffect(() => {
    setLocalDeveloperMode(Boolean(developerMode));
  }, [developerMode]);

  const loadSettings = async () => {
    try {
      const data = await getSettings();
      setSettings(data);
      if (data.theme_mode) setLocalThemeMode(data.theme_mode);
      if (data.theme_light_accent) setLocalLightAccent(data.theme_light_accent);
      if (data.theme_dark_accent) setLocalDarkAccent(data.theme_dark_accent);
      setLocalDeveloperMode(parseDeveloperMode(data.developer_mode));
    } catch (error) {
      console.error('Failed to load settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleThemeModeChange = (mode) => {
    setLocalThemeMode(mode);
    handleSaveTheme(mode, localLightAccent, localDarkAccent);
  };

  const handleLightAccentChange = (color) => {
    setLocalLightAccent(color);
    handleSaveTheme(localThemeMode, color, localDarkAccent);
  };

  const handleDarkAccentChange = (color) => {
    setLocalDarkAccent(color);
    handleSaveTheme(localThemeMode, localLightAccent, color);
  };

  const handleLocaleChange = (nextLocale) => {
    setLocale(nextLocale);
    setLocalLocale(getLocale());
    onLocaleChange?.(getLocale());
  };

  const handleDeveloperModeChange = async (nextDeveloperMode) => {
    setLocalDeveloperMode(nextDeveloperMode);
    onDeveloperModeChange?.(nextDeveloperMode);
    try {
      const saved = await updateSettings({ developer_mode: nextDeveloperMode });
      setSettings((prev) => ({ ...prev, developer_mode: nextDeveloperMode }));
      onAppSettingsSaved?.({ developer_mode: nextDeveloperMode, ...saved });
    } catch (error) {
      console.error('Failed to save developer mode:', error);
      setLocalDeveloperMode((prev) => !prev);
      onDeveloperModeChange?.(!nextDeveloperMode);
    }
  };

  const handleSaveTheme = async (mode, lightColor, darkColor) => {
    try {
      await updateSettings({
        theme_mode: mode,
        theme_light_accent: lightColor,
        theme_dark_accent: darkColor,
      });
      if (onThemeChange) {
        onThemeChange(mode, lightColor, darkColor);
      }
    } catch (error) {
      console.error('Failed to save theme settings:', error);
    }
  };

  const handleSave = async () => {
    try {
      const pollSec = clampServiceStatusPollSec(settings.service_status_poll_interval_sec);
      const payload = { ...settings, service_status_poll_interval_sec: pollSec };
      delete payload.server_port_active;
      delete payload.server_port_source;
      delete payload.server_port_restart_required;
      delete payload.server_port_last_active;

      if (settings.server_port_source === 'env') {
        delete payload.server_port;
      } else {
        const serverPort = parseInt(String(settings.server_port ?? ''), 10);
        if (
          Number.isNaN(serverPort) ||
          serverPort < SERVER_PORT_MIN ||
          serverPort > SERVER_PORT_MAX
        ) {
          alert(t('settings.server_port.invalid', { min: SERVER_PORT_MIN, max: SERVER_PORT_MAX }));
          return;
        }
        payload.server_port = serverPort;
      }
      setSaving(true);
      const saved = await updateSettings(payload);
      const { status: _status, ...savedSettings } = saved;
      setSettings((prev) => ({
        ...prev,
        ...savedSettings,
        service_status_poll_interval_sec: pollSec,
        server_port: payload.server_port ?? prev.server_port,
      }));
      alert(t('settings.save_success'));
      if (typeof onAppSettingsSaved === 'function') {
        onAppSettingsSaved(payload);
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
      alert(t('settings.save_failed'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="loading">{t('settings.loading')}</div>;
  }

  const localeOptions = SUPPORTED_LOCALES;

  const serverPortSource = settings.server_port_source || 'config';
  const serverPortEnvOverride = serverPortSource === 'env';
  const serverPortRestartRequired = Boolean(settings.server_port_restart_required);

  return (
    <div className="settings-tab tab-view" data-tour="settings">
      <h2>{t('settings.title')}</h2>

      <div className="settings-form">
        <div className="settings-section" data-tour="settings-language">
          <h3>{t('settings.language.title')}</h3>
          <p className="settings-form-hint coreui-text-muted-sm">{t('settings.language.hint')}</p>
          <div className="form-group">
            <div className="locale-picker" role="radiogroup" aria-label={t('settings.language.title')}>
              {localeOptions.map((item) => (
                <label
                  key={item.id}
                  className={`locale-picker__option ${localLocale === item.id ? 'locale-picker__option--active' : ''}`}
                >
                  <input
                    type="radio"
                    name="coreui-locale"
                    value={item.id}
                    checked={localLocale === item.id}
                    onChange={() => handleLocaleChange(item.id)}
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h3>{t('settings.theme.title')}</h3>

          <div className="form-group">
            <label>{t('settings.theme.mode_label')}</label>
            <div className="radio-group">
              <label className="radio-option">
                <input
                  type="radio"
                  name="theme-mode"
                  value="system"
                  checked={localThemeMode === 'system'}
                  onChange={(e) => handleThemeModeChange(e.target.value)}
                />
                <span>{t('settings.theme.mode.system')}</span>
              </label>
              <label className="radio-option">
                <input
                  type="radio"
                  name="theme-mode"
                  value="light"
                  checked={localThemeMode === 'light'}
                  onChange={(e) => handleThemeModeChange(e.target.value)}
                />
                <span>{t('settings.theme.mode.light')}</span>
              </label>
              <label className="radio-option">
                <input
                  type="radio"
                  name="theme-mode"
                  value="dark"
                  checked={localThemeMode === 'dark'}
                  onChange={(e) => handleThemeModeChange(e.target.value)}
                />
                <span>{t('settings.theme.mode.dark')}</span>
              </label>
            </div>
          </div>

          {(localThemeMode === 'light' || localThemeMode === 'system') && (
            <div className="form-group">
              <label>{t('settings.theme.light_accent')}</label>
              <div className="color-picker">
                {ACCENT_COLORS.map((color) => (
                  <button
                    key={`light-${color.id}`}
                    type="button"
                    className={`color-option ${localLightAccent === color.id ? 'active' : ''}`}
                    style={{ '--color-preview': color.light }}
                    onClick={() => handleLightAccentChange(color.id)}
                    title={t(`settings.theme.accent.${color.id}`)}
                  ></button>
                ))}
              </div>
            </div>
          )}

          {(localThemeMode === 'dark' || localThemeMode === 'system') && (
            <div className="form-group">
              <label>{t('settings.theme.dark_accent')}</label>
              <div className="color-picker">
                {ACCENT_COLORS.map((color) => (
                  <button
                    key={`dark-${color.id}`}
                    type="button"
                    className={`color-option ${localDarkAccent === color.id ? 'active' : ''}`}
                    style={{ '--color-preview': color.dark }}
                    onClick={() => handleDarkAccentChange(color.id)}
                    title={t(`settings.theme.accent.${color.id}`)}
                  ></button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="settings-section">
          <h3>{t('settings.general.title')}</h3>

          <div className="form-group form-group--switch">
            <div className="coreui-switch-row">
              <span className="coreui-switch-label">{t('settings.developer_mode.label')}</span>
              <label className="coreui-switch" htmlFor="coreui-developer-mode">
                <input
                  id="coreui-developer-mode"
                  type="checkbox"
                  checked={localDeveloperMode}
                  onChange={(e) => handleDeveloperModeChange(e.target.checked)}
                  aria-label={t('settings.developer_mode.label')}
                />
                <span aria-hidden="true" />
              </label>
            </div>
            <p className="settings-form-hint coreui-text-muted-sm">
              {t('settings.developer_mode.hint')}
            </p>
          </div>

          <div className="form-group">
            <label>{t('settings.tour.label')}</label>
            <p className="settings-form-hint coreui-text-muted-sm">{t('settings.tour.hint')}</p>
            <CoreUIButton type="button" variant="default" onClick={restartFirstRunTour}>
              {t('settings.tour.restart')}
            </CoreUIButton>
          </div>

          <div className="form-group">
            <label>{t('settings.db_path.label')}</label>
            <input
              type="text"
              value={settings.db_path || 'logs/webui.db'}
              onChange={(e) => handleChange('db_path', e.target.value)}
              placeholder={t('settings.db_path.placeholder')}
            />
          </div>

          <div className="form-group">
            <label>{t('settings.server_port.label')}</label>
            <p className="settings-form-hint coreui-text-muted-sm">
              {serverPortEnvOverride
                ? t('settings.server_port.hint_env', {
                    port: settings.server_port_active || settings.server_port,
                  })
                : serverPortRestartRequired
                  ? t('settings.server_port.hint_switch', {
                      active: settings.server_port_active,
                      next: settings.server_port,
                    })
                  : t('settings.server_port.hint_restart')}
            </p>
            <input
              type="number"
              value={settings.server_port || 8080}
              onChange={(e) =>
                handleChange(
                  'server_port',
                  e.target.value === '' ? '' : parseInt(e.target.value, 10),
                )
              }
              min={SERVER_PORT_MIN}
              max={SERVER_PORT_MAX}
              step={1}
              disabled={serverPortEnvOverride}
            />
          </div>

          <div className="form-group">
            <label>{t('settings.log_poll.label')}</label>
            <input
              type="number"
              value={settings.log_poll_interval || 3000}
              onChange={(e) => handleChange('log_poll_interval', parseInt(e.target.value))}
              min="1000"
              step="1000"
            />
          </div>

          <div className="form-group">
            <label>{t('settings.service_poll.label')}</label>
            <p className="settings-form-hint coreui-text-muted-sm">{t('settings.service_poll.hint')}</p>
            <input
              type="number"
              value={
                settings.service_status_poll_interval_sec !== undefined &&
                settings.service_status_poll_interval_sec !== ''
                  ? settings.service_status_poll_interval_sec
                  : SERVICE_STATUS_POLL_DEFAULT
              }
              onChange={(e) =>
                handleChange(
                  'service_status_poll_interval_sec',
                  e.target.value === '' ? '' : parseInt(e.target.value, 10),
                )
              }
              min={SERVICE_STATUS_POLL_MIN}
              max={SERVICE_STATUS_POLL_MAX}
              step={1}
            />
          </div>

          <button className="save-button" onClick={handleSave} disabled={saving}>
            {saving ? t('settings.saving') : t('settings.save')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SettingsTab;
