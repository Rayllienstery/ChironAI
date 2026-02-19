import React, { useState, useEffect } from 'react';
import { getModels, getPrompts, getModelSettings, updateModelSettings } from '../services/api';
import './ModelSettings.css';

function ModelSettings({ sessionId }) {
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [settings, setSettings] = useState({
    model: '',
    prompt_name: '',
    swift_mode: 'default',
    temperature: 0.0,
    top_p: 0.1,
    reasoning_level: '',
    code_only: false,
    include_rag_metadata: true,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [modelsData, promptsData, settingsData] = await Promise.all([
        getModels(),
        getPrompts(),
        getModelSettings(),
      ]);
      
      setModels(modelsData);
      setPrompts(promptsData.prompts || []);
      
      if (settingsData) {
        setSettings(prev => ({ ...prev, ...settingsData }));
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateModelSettings(settings);
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
    <div className="model-settings">
      <h2>Model Settings</h2>
      
      <div className="settings-form">
        <div className="form-group">
          <label>Model</label>
          <select
            value={settings.model}
            onChange={(e) => handleChange('model', e.target.value)}
          >
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Prompt Template</label>
          <select
            value={settings.prompt_name}
            onChange={(e) => handleChange('prompt_name', e.target.value)}
          >
            <option value="">Default</option>
            {prompts.map((prompt) => (
              <option key={prompt.id} value={prompt.name}>
                {prompt.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Swift Mode</label>
          <select
            value={settings.swift_mode}
            onChange={(e) => handleChange('swift_mode', e.target.value)}
          >
            <option value="default">Default</option>
            <option value="swift5">Swift 5</option>
            <option value="swift6">Swift 6</option>
          </select>
        </div>

        <div className="form-group">
          <label>
            Temperature: {settings.temperature.toFixed(1)}
          </label>
          <input
            type="range"
            min="0"
            max="20"
            step="0.1"
            value={settings.temperature * 10}
            onChange={(e) => handleChange('temperature', parseFloat(e.target.value) / 10)}
          />
        </div>

        <div className="form-group">
          <label>
            Top-p: {settings.top_p.toFixed(1)}
          </label>
          <input
            type="range"
            min="0"
            max="10"
            step="0.1"
            value={settings.top_p * 10}
            onChange={(e) => handleChange('top_p', parseFloat(e.target.value) / 10)}
          />
        </div>

        <div className="form-group">
          <label>Reasoning Level</label>
          <select
            value={settings.reasoning_level}
            onChange={(e) => handleChange('reasoning_level', e.target.value)}
          >
            <option value="">Auto</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.code_only}
              onChange={(e) => handleChange('code_only', e.target.checked)}
            />
            Code only
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.include_rag_metadata}
              onChange={(e) => handleChange('include_rag_metadata', e.target.checked)}
            />
            Include RAG metadata
          </label>
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

export default ModelSettings;

