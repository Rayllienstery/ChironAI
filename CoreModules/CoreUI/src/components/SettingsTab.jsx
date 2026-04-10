import React, { useState, useEffect } from 'react';
import { getSettings, updateSettings } from '../services/api';
import '../styles/components/SettingsTab.css';
import '../styles/components/DashboardTab.css';

const ACCENT_COLORS = [
  { id: 'purple', name: 'Purple', light: '#6750A4', dark: '#D0BCFF' },
  { id: 'cyan', name: 'Cyan', light: '#00BCD4', dark: '#4DD0E1' },
  { id: 'dark-green', name: 'Dark Green', light: '#4CAF50', dark: '#81C784' },
  { id: 'blue', name: 'Blue', light: '#2196F3', dark: '#64B5F6' },
  { id: 'orange', name: 'Orange', light: '#FF9800', dark: '#FFB74D' },
  { id: 'red', name: 'Red', light: '#F44336', dark: '#E57373' },
  { id: 'pink', name: 'Pink', light: '#E91E63', dark: '#F06292' },
  { id: 'teal', name: 'Teal', light: '#009688', dark: '#4DB6AC' },
  { id: 'indigo', name: 'Indigo', light: '#3F51B5', dark: '#7986CB' },
  { id: 'amber', name: 'Amber', light: '#FFC107', dark: '#FFD54F' },
  { id: 'slate', name: 'Slate', light: '#344767', dark: '#90A4AE' },
];

const SERVICE_STATUS_POLL_DEFAULT = 5;
const SERVICE_STATUS_POLL_MIN = 2;
const SERVICE_STATUS_POLL_MAX = 300;

function clampServiceStatusPollSec(raw) {
  const n = parseInt(String(raw ?? ''), 10);
  if (Number.isNaN(n)) return SERVICE_STATUS_POLL_DEFAULT;
  return Math.min(SERVICE_STATUS_POLL_MAX, Math.max(SERVICE_STATUS_POLL_MIN, n));
}

function SettingsTab({ themeMode, lightAccent, darkAccent, onThemeChange, onAppSettingsSaved }) {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [localThemeMode, setLocalThemeMode] = useState(themeMode || 'system');
  const [localLightAccent, setLocalLightAccent] = useState(lightAccent || 'purple');
  const [localDarkAccent, setLocalDarkAccent] = useState(darkAccent || 'cyan');

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    if (themeMode) setLocalThemeMode(themeMode);
    if (lightAccent) setLocalLightAccent(lightAccent);
    if (darkAccent) setLocalDarkAccent(darkAccent);
  }, [themeMode, lightAccent, darkAccent]);

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
    setSettings(prev => ({ ...prev, [key]: value }));
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
    setSaving(true);
    try {
      const pollSec = clampServiceStatusPollSec(settings.service_status_poll_interval_sec);
      const payload = { ...settings, service_status_poll_interval_sec: pollSec };
      await updateSettings(payload);
      setSettings((prev) => ({ ...prev, service_status_poll_interval_sec: pollSec }));
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

  return (
    <div className="settings-tab">
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
                  >
                  </button>
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
                  >
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="settings-section">
          <h3>General</h3>
          
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
            <p style={{ margin: '0 0 4px 0', fontSize: '0.875rem', opacity: 0.85 }}>
              How often the app refreshes Ollama, Open WebUI, and RAG/Qdrant status (sidebar dots and polling).
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

          <button
            className="save-button"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SettingsTab;

