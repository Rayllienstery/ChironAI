import { useState, useEffect } from 'react';
import { getSettings, updateSettings } from '../services/api';
import { SUPPORTED_LOCALES, getLocale, setLocale } from '../services/i18n';
import '../styles/components/SettingsTab.css';
import '../styles/components/DashboardTab.css';

const ACCENT_COLORS = [
  { id: 'purple', name: 'Purple', light: '#6750A4', dark: '#D0BCFF' },
  { id: 'blue', name: 'Blue', light: '#005AC1', dark: '#ABC7FF' },
  { id: 'dark-green', name: 'Green', light: '#2E7D32', dark: '#81C784' },
  { id: 'cyan', name: 'Cyan', light: '#006780', dark: '#5DD4FC' },
  { id: 'teal', name: 'Teal', light: '#006A60', dark: '#82D5C8' },
  { id: 'orange', name: 'Orange', light: '#8B5000', dark: '#FFB873' },
  { id: 'red', name: 'Red', light: '#BA1A1A', dark: '#FFB4AB' },
  { id: 'pink', name: 'Pink', light: '#984061', dark: '#FFB0C8' },
  { id: 'indigo', name: 'Indigo', light: '#3D5AA9', dark: '#B8C4FF' },
  { id: 'amber', name: 'Amber', light: '#7D5700', dark: '#F2C029' },
  { id: 'slate', name: 'Slate', light: '#4A6572', dark: '#B0C9D6' },
  { id: 'lime', name: 'Lime', light: '#4A6B00', dark: '#C6E063' },
  { id: 'violet', name: 'Violet', light: '#5B3F94', dark: '#CBBEFF' },
  { id: 'coral', name: 'Coral', light: '#9E4242', dark: '#FFB3B0' },
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

function SettingsTab({ themeMode, lightAccent, darkAccent, locale, onThemeChange, onLocaleChange, onAppSettingsSaved }) {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [localThemeMode, setLocalThemeMode] = useState(themeMode || 'system');
  const [localLightAccent, setLocalLightAccent] = useState(lightAccent || 'purple');
  const [localDarkAccent, setLocalDarkAccent] = useState(darkAccent || 'cyan');
  const [localLocale, setLocalLocale] = useState(locale || getLocale());

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    if (themeMode) setLocalThemeMode(themeMode);
    if (lightAccent) setLocalLightAccent(lightAccent);
    if (darkAccent) setLocalDarkAccent(darkAccent);
    if (locale) setLocalLocale(locale);
  }, [themeMode, lightAccent, darkAccent, locale]);

  const loadSettings = async () => {
    try {
      const data = await getSettings();
      setSettings(data);
      if (data.theme_mode) setLocalThemeMode(data.theme_mode);
      if (data.theme_light_accent) setLocalLightAccent(data.theme_light_accent);
      if (data.theme_dark_accent) setLocalDarkAccent(data.theme_dark_accent);
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
          alert(`Server port must be between ${SERVER_PORT_MIN} and ${SERVER_PORT_MAX}`);
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
      alert('Settings saved successfully');
      if (typeof onAppSettingsSaved === 'function') {
        onAppSettingsSaved(payload);
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
      alert('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading settings...</div>;
  }

  const serverPortSource = settings.server_port_source || 'config';
  const serverPortEnvOverride = serverPortSource === 'env';
  const serverPortRestartRequired = Boolean(settings.server_port_restart_required);

  return (
    <div className="settings-tab tab-view">
      <h2>Settings</h2>

      <div className="settings-form">
        <div className="settings-section">
          <h3>Theme</h3>

          <div className="form-group">
            <label>Theme Mode</label>
            <div className="radio-group">
              <label className="radio-option">
                <input
                  type="radio"
                  name="theme-mode"
                  value="system"
                  checked={localThemeMode === 'system'}
                  onChange={(e) => handleThemeModeChange(e.target.value)}
                />
                <span>System</span>
              </label>
              <label className="radio-option">
                <input
                  type="radio"
                  name="theme-mode"
                  value="light"
                  checked={localThemeMode === 'light'}
                  onChange={(e) => handleThemeModeChange(e.target.value)}
                />
                <span>Light</span>
              </label>
              <label className="radio-option">
                <input
                  type="radio"
                  name="theme-mode"
                  value="dark"
                  checked={localThemeMode === 'dark'}
                  onChange={(e) => handleThemeModeChange(e.target.value)}
                />
                <span>Dark</span>
              </label>
            </div>
          </div>

          {(localThemeMode === 'light' || localThemeMode === 'system') && (
            <div className="form-group">
              <label>Light Theme Accent Color</label>
              <div className="color-picker">
                {ACCENT_COLORS.map((color) => (
                  <button
                    key={`light-${color.id}`}
                    type="button"
                    className={`color-option ${localLightAccent === color.id ? 'active' : ''}`}
                    style={{ '--color-preview': color.light }}
                    onClick={() => handleLightAccentChange(color.id)}
                    title={color.name}
                  ></button>
                ))}
              </div>
            </div>
          )}

          {(localThemeMode === 'dark' || localThemeMode === 'system') && (
            <div className="form-group">
              <label>Dark Theme Accent Color</label>
              <div className="color-picker">
                {ACCENT_COLORS.map((color) => (
                  <button
                    key={`dark-${color.id}`}
                    type="button"
                    className={`color-option ${localDarkAccent === color.id ? 'active' : ''}`}
                    style={{ '--color-preview': color.dark }}
                    onClick={() => handleDarkAccentChange(color.id)}
                    title={color.name}
                  ></button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="settings-section">
          <h3>General</h3>

          <div className="form-group">
            <label htmlFor="coreui-locale-select">Interface language</label>
            <select
              id="coreui-locale-select"
              value={localLocale}
              onChange={(e) => handleLocaleChange(e.target.value)}
            >
              {SUPPORTED_LOCALES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Database Path</label>
            <input
              type="text"
              value={settings.db_path || 'logs/webui.db'}
              onChange={(e) => handleChange('db_path', e.target.value)}
              placeholder="logs/webui.db"
            />
          </div>

          <div className="form-group">
            <label>Server Port</label>
            <p className="settings-form-hint coreui-text-muted-sm">
              {serverPortEnvOverride
                ? `SERVER_PORT is set, so this process uses ${settings.server_port_active || settings.server_port}.`
                : serverPortRestartRequired
                  ? `Restart the app to switch from ${settings.server_port_active} to ${settings.server_port}.`
                  : 'Changing the server port takes effect after restarting the app.'}
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
            <label>Log Auto-Update Interval (ms)</label>
            <input
              type="number"
              value={settings.log_poll_interval || 3000}
              onChange={(e) => handleChange('log_poll_interval', parseInt(e.target.value))}
              min="1000"
              step="1000"
            />
          </div>

          <div className="form-group">
            <label>Service status poll interval (seconds)</label>
            <p className="settings-form-hint coreui-text-muted-sm">
              How often the app refreshes extension, provider, and RAG/Qdrant status (sidebar dots
              and polling).
            </p>
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
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SettingsTab;
