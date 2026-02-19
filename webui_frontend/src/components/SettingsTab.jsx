import React, { useState, useEffect } from 'react';
import { getSettings, updateSettings } from '../services/api';
import './SettingsTab.css';

function SettingsTab() {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await getSettings();
      setSettings(data);
    } catch (error) {
      console.error('Failed to load settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSettings(settings);
      alert('Settings saved successfully');
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

        <button
          className="save-button"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}

export default SettingsTab;

