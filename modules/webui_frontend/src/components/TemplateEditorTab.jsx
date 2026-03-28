import React, { useState, useEffect } from 'react';
import {
  getPrompts,
  getPromptContent,
  createPrompt,
  updatePrompt,
  deletePrompt,
  getTrashPrompts,
  getTrashPromptContent,
  updateTrashPrompt,
  restorePrompt,
  clearTrash,
} from '../services/api';
import './TemplateEditorTab.css';

function TemplateEditorTab() {
  const [prompts, setPrompts] = useState([]);
  const [selectedPromptName, setSelectedPromptName] = useState(null);
  const [editorFields, setEditorFields] = useState({
    title: '',
    description: '',
    body: '',
    rawContent: '',
  });
  const [isDirty, setIsDirty] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [error, setError] = useState(null);
  const [renamePromptName, setRenamePromptName] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [editMode, setEditMode] = useState('structured'); // 'structured' or 'raw'
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [viewMode, setViewMode] = useState('templates'); // 'templates' or 'trash'
  const [trashPrompts, setTrashPrompts] = useState([]);
  const [selectedTrashName, setSelectedTrashName] = useState(null);
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [helpModalTab, setHelpModalTab] = useState('tips'); // 'tips', 'linter', 'structure'
  const [linterWarnings, setLinterWarnings] = useState([]);

  const promptTips = [
    "Be specific and concrete: Instead of 'make it better', specify what exactly needs improvement (performance, readability, error handling).",
    "Provide context: Include relevant background information, constraints, and the problem you're trying to solve.",
    "Use examples: Show input/output examples or code snippets to illustrate what you want.",
    "Define the format: Specify the desired output format (code, explanation, step-by-step guide, etc.).",
    "Set constraints: Mention limitations (language version, libraries, performance requirements, platform).",
    "Break down complex tasks: Split large requests into smaller, manageable sub-tasks.",
    "Specify the audience: Indicate who will use/read the output (beginners, experts, end-users).",
    "Include error scenarios: Mention edge cases, error handling, and what should happen in failure cases.",
    "Use domain terminology: Use precise technical terms relevant to your field (API names, patterns, concepts).",
    "Request reasoning: Ask for explanations of why certain approaches are chosen, not just what to do.",
    "Specify testing requirements: Mention if you need unit tests, integration tests, or test cases.",
    "Define success criteria: Clearly state how you'll know the solution is correct or complete.",
    "Mention style preferences: Specify coding style, documentation format, naming conventions.",
    "Include performance expectations: Mention if speed, memory usage, or scalability are concerns.",
    "Request alternatives: Ask for multiple approaches and trade-offs between them.",
    "Specify dependencies: List what libraries, frameworks, or tools can be used.",
    "Include security considerations: Mention if security, privacy, or data protection are important.",
    "Request validation: Ask for input validation, error checking, and defensive programming.",
    "Specify maintainability: Mention if code should be easy to modify, extend, or debug.",
    "Use structured format: Organize your prompt with clear sections (Context, Requirements, Constraints, Expected Output)."
  ];

  const isReadme = (name) => {
    return name && name.toLowerCase() === 'readme';
  };

  const assembleContentFromFields = (fields) => {
    let content = '';
    if (fields.title) {
      content += `# ${fields.title}\n\n`;
    }
    if (fields.description) {
      content += `${fields.description}\n\n`;
    }
    if (fields.body) {
      content += fields.body;
    }
    return content.trim();
  };

  const assembleContent = () => {
    if (editMode === 'raw') {
      return editorFields.rawContent;
    }
    return assembleContentFromFields(editorFields);
  };

  const runPromptLinter = (text) => {
    const warnings = [];
    const lowerText = text.toLowerCase();
    
    // Check for explicit constraints
    if (!lowerText.includes('constraint') && 
        !lowerText.includes('limit') && 
        !lowerText.includes('requirement') &&
        !lowerText.includes('must') &&
        !lowerText.includes('should') &&
        !lowerText.includes('cannot')) {
      warnings.push({
        type: 'missing_constraints',
        message: 'No explicit constraints mentioned (limitations, requirements, must/should/cannot)',
        severity: 'warning'
      });
    }
    
    // Check for architecture
    const architectureKeywords = ['architecture', 'mvvm', 'mvc', 'clean', 'pattern', 'structure', 'design pattern'];
    if (!architectureKeywords.some(keyword => lowerText.includes(keyword))) {
      warnings.push({
        type: 'missing_architecture',
        message: 'No architecture specified (MVVM, MVC, Clean, pattern, structure)',
        severity: 'warning'
      });
    }
    
    // Check for format requirements
    const formatKeywords = ['format', 'output format', 'structure', 'layout', 'style', 'template'];
    if (!formatKeywords.some(keyword => lowerText.includes(keyword))) {
      warnings.push({
        type: 'missing_format',
        message: 'No output format specified (format, structure, layout, style)',
        severity: 'info'
      });
    }
    
    // Check for Swift version
    const swiftVersionKeywords = ['swift', 'ios', 'swift 5', 'swift 6', 'swiftui', 'version'];
    if (!swiftVersionKeywords.some(keyword => lowerText.includes(keyword))) {
      warnings.push({
        type: 'missing_swift_version',
        message: 'No Swift/iOS version specified',
        severity: 'warning'
      });
    }
    
    // Check for context
    if (text.length < 50) {
      warnings.push({
        type: 'insufficient_context',
        message: 'Prompt seems too short - may lack context',
        severity: 'info'
      });
    }
    
    return warnings;
  };

  const structurePrompt = (text) => {
    const lines = text.split('\n').map(l => l.trim()).filter(l => l);
    
    const sections = {
      context: [],
      constraints: [],
      architecture: [],
      expectedOutput: []
    };
    
    let currentSection = 'context';
    const sectionKeywords = {
      context: ['context', 'background', 'situation', 'problem', 'scenario'],
      constraints: ['constraint', 'limit', 'requirement', 'must', 'should', 'cannot', 'restriction'],
      architecture: ['architecture', 'mvvm', 'mvc', 'clean', 'pattern', 'structure', 'design'],
      expectedOutput: ['output', 'result', 'format', 'structure', 'should return', 'expected']
    };
    
    lines.forEach(line => {
      const lowerLine = line.toLowerCase();
      
      // Check if line indicates a section
      for (const [section, keywords] of Object.entries(sectionKeywords)) {
        if (keywords.some(keyword => lowerLine.includes(keyword))) {
          currentSection = section;
          break;
        }
      }
      
      sections[currentSection].push(line);
    });
    
    // Build structured prompt
    let structured = '';
    if (sections.context.length > 0) {
      structured += `## Context\n${sections.context.join('\n')}\n\n`;
    }
    if (sections.constraints.length > 0) {
      structured += `## Constraints\n${sections.constraints.join('\n')}\n\n`;
    }
    if (sections.architecture.length > 0) {
      structured += `## Architecture\n${sections.architecture.join('\n')}\n\n`;
    }
    if (sections.expectedOutput.length > 0) {
      structured += `## Expected Output\n${sections.expectedOutput.join('\n')}\n\n`;
    }
    
    // If no sections were detected, put everything in context
    if (!structured) {
      structured = `## Context\n${text}\n\n`;
    }
    
    return structured.trim();
  };

  const handleLintPrompt = () => {
    const currentText = editMode === 'raw' 
      ? editorFields.rawContent 
      : assembleContent();
    const warnings = runPromptLinter(currentText);
    setLinterWarnings(warnings);
    setHelpModalTab('linter');
    setShowHelpModal(true);
  };

  const handleStructurePrompt = () => {
    const currentText = editMode === 'raw' 
      ? editorFields.rawContent 
      : assembleContent();
    const structured = structurePrompt(currentText);
    
    if (editMode === 'raw') {
      setEditorFields(prev => ({ ...prev, rawContent: structured }));
    } else {
      // Try to parse structured content back
      const lines = structured.split('\n');
      let title = '';
      let description = '';
      let body = structured;
      
      if (lines.length > 0 && lines[0].startsWith('## ')) {
        title = lines[0].substring(3);
        body = lines.slice(1).join('\n');
      }
      
      setEditorFields(prev => ({
        ...prev,
        title: title,
        description: '',
        body: body.trim(),
        rawContent: structured
      }));
    }
    setIsDirty(true);
  };

  useEffect(() => {
    if (viewMode === 'templates') {
      loadPrompts();
    } else {
      loadTrashPrompts();
    }
  }, [viewMode]);

  useEffect(() => {
    // Real-time intelligent hints
    try {
      if (viewMode === 'templates' && selectedPromptName && !isReadme(selectedPromptName)) {
        const currentText = editMode === 'raw' 
          ? editorFields.rawContent 
          : assembleContent();
        const warnings = runPromptLinter(currentText);
        setLinterWarnings(warnings);
      } else if (viewMode === 'trash' && selectedTrashName) {
        const currentText = editMode === 'raw' 
          ? editorFields.rawContent 
          : assembleContent();
        const warnings = runPromptLinter(currentText);
        setLinterWarnings(warnings);
      } else {
        setLinterWarnings([]);
      }
    } catch (error) {
      console.error('Error in linter useEffect:', error);
      setLinterWarnings([]);
    }
  }, [editorFields, editMode, selectedPromptName, selectedTrashName, viewMode]);

  useEffect(() => {
    if (viewMode === 'templates' && selectedPromptName) {
      loadPromptContent(selectedPromptName);
    } else if (viewMode === 'trash' && selectedTrashName) {
      loadTrashPromptContent(selectedTrashName);
    } else {
      setEditorFields({
        title: '',
        description: '',
        body: '',
        rawContent: '',
      });
      setIsDirty(false);
    }
  }, [selectedPromptName, selectedTrashName, viewMode]);

  const loadPrompts = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getPrompts();
      // getPrompts() returns { prompts: [...] }
      setPrompts(data?.prompts || []);
    } catch (e) {
      setError(e.message);
      console.error('Failed to load prompts:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const loadTrashPrompts = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getTrashPrompts();
      setTrashPrompts(data.prompts || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  const loadTrashPromptContent = async (trashName) => {
    setIsLoadingContent(true);
    setError(null);
    try {
      const data = await getTrashPromptContent(trashName);
      const content = data.content || '';
      
      // Parse structured content same way as regular prompts
      const lines = content.split('\n');
      let title = '';
      let description = '';
      let body = content;
      
      if (lines.length > 0 && lines[0].trim()) {
        const firstLine = lines[0].trim();
        if (firstLine.startsWith('# ')) {
          title = firstLine.substring(2);
          body = lines.slice(1).join('\n');
        } else if (firstLine.length < 100) {
          title = firstLine;
          body = lines.slice(1).join('\n');
        }
      }
      
      if (lines.length > 1 && lines[1].trim() && !lines[1].trim().startsWith('#')) {
        description = lines[1].trim();
        if (title) {
          body = lines.slice(2).join('\n');
        } else {
          body = lines.slice(1).join('\n');
        }
      }
      
      setEditorFields({
        title: title,
        description: description,
        body: body.trim(),
        rawContent: content,
      });
      setIsDirty(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoadingContent(false);
    }
  };

  const loadPromptContent = async (name) => {
    setIsLoadingContent(true);
    setError(null);
    try {
      const data = await getPromptContent(name);
      const content = data.content || '';
      
      // Try to parse structured content
      // Look for title/description patterns or use raw content
      const lines = content.split('\n');
      let title = '';
      let description = '';
      let body = content;
      
      // Simple heuristic: first line might be title, second might be description
      if (lines.length > 0 && lines[0].trim()) {
        const firstLine = lines[0].trim();
        if (firstLine.startsWith('# ')) {
          title = firstLine.substring(2);
          body = lines.slice(1).join('\n');
        } else if (firstLine.length < 100) {
          title = firstLine;
          body = lines.slice(1).join('\n');
        }
      }
      
      if (lines.length > 1 && lines[1].trim() && !lines[1].trim().startsWith('#')) {
        description = lines[1].trim();
        if (title) {
          body = lines.slice(2).join('\n');
        } else {
          body = lines.slice(1).join('\n');
        }
      }
      
      setEditorFields({
        title: title,
        description: description,
        body: body.trim(),
        rawContent: content,
      });
      setIsDirty(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoadingContent(false);
    }
  };

  const handleFieldChange = (field, value) => {
    setEditorFields(prev => {
      const updated = { ...prev, [field]: value };
      // Update rawContent when structured fields change
      if (field !== 'rawContent' && editMode === 'structured') {
        const newContent = assembleContentFromFields(updated);
        updated.rawContent = newContent;
        // Real-time linting
        setTimeout(() => {
          const warnings = runPromptLinter(newContent);
          setLinterWarnings(warnings);
        }, 100);
      }
      return updated;
    });
    setIsDirty(true);
  };

  const handleRawContentChange = (value) => {
    setEditorFields(prev => ({ ...prev, rawContent: value }));
    setIsDirty(true);
    // Real-time linting
    const warnings = runPromptLinter(value);
    setLinterWarnings(warnings);
  };

  // Removed duplicate useEffect - already handled above

  const handleSave = async () => {
    if (viewMode === 'templates') {
      if (!selectedPromptName) return;
      
      if (isReadme(selectedPromptName)) {
        setError('README cannot be edited');
        return;
      }
      
      setIsSaving(true);
      setError(null);
      try {
        const content = editMode === 'raw' 
          ? editorFields.rawContent 
          : assembleContent();
        
        await updatePrompt(selectedPromptName, { content });
        setIsDirty(false);
        await loadPrompts();
      } catch (e) {
        setError(e.message);
      } finally {
        setIsSaving(false);
      }
    } else if (viewMode === 'trash') {
      if (!selectedTrashName) return;
      
      setIsSaving(true);
      setError(null);
      try {
        const content = editMode === 'raw' 
          ? editorFields.rawContent 
          : assembleContent();
        
        await updateTrashPrompt(selectedTrashName, content);
        setIsDirty(false);
        await loadTrashPrompts();
      } catch (e) {
        setError(e.message);
      } finally {
        setIsSaving(false);
      }
    }
  };

  const handleDuplicate = async () => {
    if (viewMode !== 'templates' || !selectedPromptName) return;
    
    const baseName = selectedPromptName;
    let newName = `${baseName}-copy`;
    let counter = 1;
    
    // Find available name
    while (prompts.some(p => p.name === newName)) {
      newName = `${baseName}-copy-${counter}`;
      counter++;
    }
    
    setIsSaving(true);
    setError(null);
    try {
      await createPrompt({
        sourceName: selectedPromptName,
        name: newName,
      });
      await loadPrompts();
      setSelectedPromptName(newName);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedPromptName) return;
    
    const confirmed = window.confirm(
      `Move template "${selectedPromptName}" to trash?\n\nYou can restore it later from the trash.`
    );
    if (!confirmed) {
      return;
    }
    
    setIsSaving(true);
    setError(null);
    try {
      await deletePrompt(selectedPromptName);
      await loadPrompts();
      setSelectedPromptName(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleRenameStart = () => {
    setRenamePromptName(selectedPromptName);
    setRenameValue(selectedPromptName);
  };

  const handleRenameCancel = () => {
    setRenamePromptName(null);
    setRenameValue('');
  };

  const handleRenameSave = async () => {
    if (!renamePromptName || !renameValue || renameValue === renamePromptName) {
      handleRenameCancel();
      return;
    }
    
    // Prevent renaming to README
    if (isReadme(renameValue)) {
      setError('Cannot rename to README');
      return;
    }
    
    setIsSaving(true);
    setError(null);
    try {
      await updatePrompt(renamePromptName, { newName: renameValue });
      await loadPrompts();
      setSelectedPromptName(renameValue);
      handleRenameCancel();
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSelectPrompt = (name) => {
    if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) {
      return;
    }
    if (viewMode === 'templates') {
      setSelectedPromptName(name);
      setSelectedTrashName(null);
    } else {
      setSelectedTrashName(name);
      setSelectedPromptName(null);
    }
    setIsCreatingNew(false);
    setNewTemplateName('');
  };

  const handleRestore = async () => {
    if (!selectedTrashName) return;
    
    setIsSaving(true);
    setError(null);
    try {
      await restorePrompt(selectedTrashName);
      await loadTrashPrompts();
      await loadPrompts();
      setSelectedTrashName(null);
      setViewMode('templates');
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleClearTrash = async () => {
    if (!window.confirm('Permanently delete all items in trash? This action cannot be undone.')) {
      return;
    }
    
    setIsSaving(true);
    setError(null);
    try {
      await clearTrash();
      await loadTrashPrompts();
      setSelectedTrashName(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateNew = () => {
    if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) {
      return;
    }
    setIsCreatingNew(true);
    setNewTemplateName('');
    setSelectedPromptName(null);
    setEditorFields({
      title: '',
      description: '',
      body: '',
      rawContent: '',
    });
    setIsDirty(false);
  };

  const handleCreateNewSave = async () => {
    if (!newTemplateName.trim()) {
      setError('Template name is required');
      return;
    }
    
    // Prevent creating README
    if (isReadme(newTemplateName.trim())) {
      setError('Cannot create a file named README');
      return;
    }
    
    if (prompts.some(p => p.name === newTemplateName.trim())) {
      setError('A template with this name already exists');
      return;
    }
    
    setIsSaving(true);
    setError(null);
    try {
      const content = editMode === 'raw' 
        ? editorFields.rawContent 
        : assembleContent();
      
      await createPrompt({
        name: newTemplateName.trim(),
        content: content || '# New Template\n\n',
      });
      await loadPrompts();
      setSelectedPromptName(newTemplateName.trim());
      setIsCreatingNew(false);
      setNewTemplateName('');
      setIsDirty(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateNewCancel = () => {
    if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) {
      return;
    }
    setIsCreatingNew(false);
    setNewTemplateName('');
    setEditorFields({
      title: '',
      description: '',
      body: '',
      rawContent: '',
    });
    setIsDirty(false);
  };

  return (
    <div className="template-editor-tab">
      <div className="template-editor-layout">
        <div className="template-list-panel">
          <div className="template-view-toggle">
            <button
              type="button"
              className={`template-view-toggle-button ${viewMode === 'templates' ? 'active' : ''}`}
              onClick={() => {
                if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) {
                  return;
                }
                setViewMode('templates');
                setSelectedPromptName(null);
                setSelectedTrashName(null);
              }}
            >
              Templates
            </button>
            <button
              type="button"
              className={`template-view-toggle-button ${viewMode === 'trash' ? 'active' : ''}`}
              onClick={() => {
                if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) {
                  return;
                }
                setViewMode('trash');
                setSelectedPromptName(null);
                setSelectedTrashName(null);
              }}
            >
              Trash
            </button>
          </div>
          <div className="template-list-header">
            <h2>{viewMode === 'templates' ? 'Templates' : 'Trash'}</h2>
            <div className="template-list-header-actions">
              {viewMode === 'templates' && (
                <button
                  type="button"
                  className="template-button primary"
                  onClick={handleCreateNew}
                  disabled={isLoading || isSaving}
                  title="Create new template"
                >
                  <span className="material-symbols-outlined">add</span>
                </button>
              )}
              {viewMode === 'trash' && (
                <button
                  type="button"
                  className="template-button delete"
                  onClick={handleClearTrash}
                  disabled={isLoading || isSaving || trashPrompts.length === 0}
                  title="Clear trash"
                >
                  <span className="material-symbols-outlined">delete_forever</span>
                </button>
              )}
              <button
                type="button"
                className="template-button ghost"
                onClick={viewMode === 'templates' ? loadPrompts : loadTrashPrompts}
                disabled={isLoading}
                title="Refresh list"
              >
                <span className="material-symbols-outlined">refresh</span>
              </button>
            </div>
          </div>
          
          {isLoading ? (
            <div className="loading">Loading {viewMode === 'templates' ? 'templates' : 'trash'}...</div>
          ) : viewMode === 'templates' ? (
            prompts.length === 0 ? (
              <div className="empty-state">No templates found</div>
            ) : (() => {
              const readmePrompts = prompts.filter(p => isReadme(p.name));
              const regularPrompts = prompts.filter(p => !isReadme(p.name));
              
              return (
                <>
                  {readmePrompts.length > 0 && (
                    <div className="template-section">
                      <div className="template-section-header">README</div>
                      <div className="template-list">
                        {readmePrompts.map((prompt) => (
                          <div
                            key={prompt.name}
                            className={`template-item readme-item ${selectedPromptName === prompt.name ? 'selected' : ''}`}
                            onClick={() => handleSelectPrompt(prompt.name)}
                          >
                            <div className="template-item-name">{prompt.name}</div>
                            {selectedPromptName === prompt.name && (
                              <div className="template-item-actions">
                                <button
                                  type="button"
                                  className="template-action-button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDuplicate();
                                  }}
                                  disabled={isSaving}
                                  title="Duplicate"
                                >
                                  <span className="material-symbols-outlined">content_copy</span>
                                </button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {regularPrompts.length > 0 && (
                    <div className="template-section">
                      <div className="template-section-header">Templates</div>
                      <div className="template-list">
                        {regularPrompts.map((prompt) => (
                          <div
                            key={prompt.name}
                            className={`template-item ${selectedPromptName === prompt.name ? 'selected' : ''}`}
                            onClick={() => handleSelectPrompt(prompt.name)}
                          >
                            <div className="template-item-name">{prompt.name}</div>
                            {selectedPromptName === prompt.name && (
                              <div className="template-item-actions">
                                <button
                                  type="button"
                                  className="template-action-button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDuplicate();
                                  }}
                                  disabled={isSaving}
                                  title="Duplicate"
                                >
                                  <span className="material-symbols-outlined">content_copy</span>
                                </button>
                                <button
                                  type="button"
                                  className="template-action-button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleRenameStart();
                                  }}
                                  disabled={isSaving}
                                  title="Rename"
                                >
                                  <span className="material-symbols-outlined">edit</span>
                                </button>
                                <button
                                  type="button"
                                  className="template-action-button delete"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDelete();
                                  }}
                                  disabled={isSaving}
                                  title="Move to trash"
                                >
                                  <span className="material-symbols-outlined">delete</span>
                                </button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              );
            })()
          ) : (
            trashPrompts.length === 0 ? (
              <div className="empty-state">Trash is empty</div>
            ) : (
              <div className="template-list">
                {trashPrompts.map((prompt) => (
                  <div
                    key={prompt.trash_name}
                    className={`template-item ${selectedTrashName === prompt.trash_name ? 'selected' : ''}`}
                    onClick={() => handleSelectPrompt(prompt.trash_name)}
                  >
                    <div className="template-item-name">{prompt.name}</div>
                    {selectedTrashName === prompt.trash_name && (
                      <div className="template-item-actions">
                        <button
                          type="button"
                          className="template-action-button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRestore();
                          }}
                          disabled={isSaving}
                          title="Restore"
                        >
                          <span className="material-symbols-outlined">restore</span>
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )
          )}
        </div>

        <div className="template-editor-panel">
          {viewMode === 'trash' && selectedTrashName ? (
            <>
              <div className="template-editor-header">
                <h2>
                  <div className="template-name-with-rename">
                    <span>{trashPrompts.find(p => p.trash_name === selectedTrashName)?.name || selectedTrashName}</span>
                    <span className="template-trash-badge">(Trash)</span>
                  </div>
                </h2>
                <div className="template-editor-actions">
                  <button
                    type="button"
                    className="template-button ghost"
                    onClick={() => setShowHelpModal(true)}
                    title="Show prompt writing tips"
                  >
                    <span className="material-symbols-outlined">help</span>
                  </button>
                  <div className="template-edit-mode-toggle">
                    <button
                      type="button"
                      className={`template-mode-button ${editMode === 'structured' ? 'active' : ''}`}
                      onClick={() => {
                        if (editMode === 'raw') {
                          const newContent = assembleContentFromFields(editorFields);
                          setEditorFields(prev => ({ ...prev, rawContent: newContent }));
                        }
                        setEditMode('structured');
                      }}
                    >
                      Structured
                    </button>
                    <button
                      type="button"
                      className={`template-mode-button ${editMode === 'raw' ? 'active' : ''}`}
                      onClick={() => {
                        if (editMode === 'structured') {
                          const newContent = assembleContentFromFields(editorFields);
                          setEditorFields(prev => ({ ...prev, rawContent: newContent }));
                        }
                        setEditMode('raw');
                      }}
                    >
                      Raw
                    </button>
                  </div>
                  <button
                    type="button"
                    className="template-button"
                    onClick={handleStructurePrompt}
                    disabled={isSaving}
                    title="Auto-structure prompt"
                  >
                    <span className="material-symbols-outlined">auto_fix_high</span>
                    Structure
                  </button>
                  <button
                    type="button"
                    className="template-button"
                    onClick={handleRestore}
                    disabled={isSaving}
                    title="Restore from trash"
                  >
                    <span className="material-symbols-outlined">restore</span>
                    Restore
                  </button>
                  <button
                    type="button"
                    className="template-button primary"
                    onClick={handleSave}
                    disabled={isSaving || isLoadingContent || !isDirty}
                  >
                    {isSaving ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </div>
              {error && <div className="template-error">Error: {error}</div>}
              {isLoadingContent ? (
                <div className="loading">Loading template content...</div>
              ) : editMode === 'structured' ? (
                <div className="template-editor-form">
                  <div className="template-field">
                    <label>Title</label>
                    <input
                      type="text"
                      value={editorFields.title}
                      onChange={(e) => handleFieldChange('title', e.target.value)}
                      placeholder="Template title (optional)"
                    />
                  </div>
                  <div className="template-field">
                    <label>Description</label>
                    <textarea
                      value={editorFields.description}
                      onChange={(e) => handleFieldChange('description', e.target.value)}
                      placeholder="Brief description (optional)"
                      rows="2"
                    />
                  </div>
                  <div className="template-field body-field">
                    <label>Body</label>
                    <textarea
                      value={editorFields.body}
                      onChange={(e) => handleFieldChange('body', e.target.value)}
                      placeholder="Template content (Markdown)"
                    />
                  </div>
                </div>
              ) : (
                <div className="template-editor-form">
                  <div className="template-field body-field">
                    <label>Raw Markdown</label>
                    <textarea
                      value={editorFields.rawContent}
                      onChange={(e) => handleRawContentChange(e.target.value)}
                      placeholder="Template content (Markdown)"
                      className="template-raw-textarea"
                    />
                  </div>
                </div>
              )}
            </>
          ) : isCreatingNew ? (
            <>
              <div className="template-editor-header">
                <h2>
                  <input
                    type="text"
                    className="template-rename-input"
                    value={newTemplateName}
                    onChange={(e) => setNewTemplateName(e.target.value)}
                    placeholder="Enter template name..."
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newTemplateName.trim()) {
                        handleCreateNewSave();
                      } else if (e.key === 'Escape') {
                        handleCreateNewCancel();
                      }
                    }}
                    autoFocus
                  />
                </h2>
                <div className="template-editor-actions">
                  <button
                    type="button"
                    className="template-button ghost"
                    onClick={() => setShowHelpModal(true)}
                    title="Show prompt writing tips"
                  >
                    <span className="material-symbols-outlined">help</span>
                  </button>
                  <div className="template-edit-mode-toggle">
                    <button
                      type="button"
                      className={`template-mode-button ${editMode === 'structured' ? 'active' : ''}`}
                      onClick={() => {
                        if (editMode === 'raw') {
                          const newContent = assembleContentFromFields(editorFields);
                          setEditorFields(prev => ({ ...prev, rawContent: newContent }));
                        }
                        setEditMode('structured');
                      }}
                    >
                      Structured
                    </button>
                    <button
                      type="button"
                      className={`template-mode-button ${editMode === 'raw' ? 'active' : ''}`}
                      onClick={() => {
                        if (editMode === 'structured') {
                          const newContent = assembleContentFromFields(editorFields);
                          setEditorFields(prev => ({ ...prev, rawContent: newContent }));
                        }
                        setEditMode('raw');
                      }}
                    >
                      Raw
                    </button>
                  </div>
                  <button
                    type="button"
                    className="template-button"
                    onClick={handleStructurePrompt}
                    disabled={isSaving}
                    title="Auto-structure prompt"
                  >
                    <span className="material-symbols-outlined">auto_fix_high</span>
                    Structure
                  </button>
                  <button
                    type="button"
                    className="template-button primary"
                    onClick={handleCreateNewSave}
                    disabled={isSaving || !newTemplateName.trim()}
                  >
                    {isSaving ? 'Creating...' : 'Create'}
                  </button>
                  <button
                    type="button"
                    className="template-button ghost"
                    onClick={handleCreateNewCancel}
                    disabled={isSaving}
                  >
                    Cancel
                  </button>
                </div>
              </div>
              {error && <div className="template-error">Error: {error}</div>}
              {editMode === 'structured' ? (
                <div className="template-editor-form">
                  <div className="template-field">
                    <label>Title</label>
                    <input
                      type="text"
                      value={editorFields.title}
                      onChange={(e) => handleFieldChange('title', e.target.value)}
                      placeholder="Template title (optional)"
                    />
                  </div>
                  <div className="template-field">
                    <label>Description</label>
                    <textarea
                      value={editorFields.description}
                      onChange={(e) => handleFieldChange('description', e.target.value)}
                      placeholder="Brief description (optional)"
                      rows="2"
                    />
                  </div>
                  <div className="template-field">
                    <label>Body</label>
                    <textarea
                      value={editorFields.body}
                      onChange={(e) => handleFieldChange('body', e.target.value)}
                      placeholder="Template content (Markdown)"
                      rows="20"
                    />
                  </div>
                </div>
              ) : (
                <div className="template-editor-form">
                  <div className="template-field">
                    <label>Raw Markdown</label>
                    <textarea
                      value={editorFields.rawContent}
                      onChange={(e) => handleRawContentChange(e.target.value)}
                      placeholder="Template content (Markdown)"
                      rows="25"
                      className="template-raw-textarea"
                    />
                  </div>
                </div>
              )}
            </>
          ) : viewMode === 'templates' && selectedPromptName ? (
            <>
              <div className="template-editor-header">
                <h2>
                  {renamePromptName === selectedPromptName ? (
                    <input
                      type="text"
                      className="template-rename-input"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          handleRenameSave();
                        } else if (e.key === 'Escape') {
                          handleRenameCancel();
                        }
                      }}
                      autoFocus
                    />
                  ) : (
                    <div className="template-name-with-rename">
                      <span>{selectedPromptName}</span>
                      <button
                        type="button"
                        className="template-rename-inline-button"
                        onClick={handleRenameStart}
                        disabled={isSaving}
                        title="Rename template"
                      >
                        <span className="material-symbols-outlined">edit</span>
                      </button>
                    </div>
                  )}
                </h2>
                {renamePromptName === selectedPromptName ? (
                  <div className="template-editor-actions">
                    <button
                      type="button"
                      className="template-button"
                      onClick={handleRenameSave}
                      disabled={isSaving || !renameValue || renameValue === renamePromptName}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="template-button ghost"
                      onClick={handleRenameCancel}
                      disabled={isSaving}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="template-editor-actions">
                    <button
                      type="button"
                      className="template-button ghost"
                      onClick={() => setShowHelpModal(true)}
                      title="Show prompt writing tips"
                    >
                      <span className="material-symbols-outlined">help</span>
                    </button>
                    <div className="template-edit-mode-toggle">
                      <button
                        type="button"
                        className={`template-mode-button ${editMode === 'structured' ? 'active' : ''}`}
                        onClick={() => {
                          // Update rawContent when switching to structured mode
                          if (editMode === 'raw') {
                            const newContent = assembleContentFromFields(editorFields);
                            setEditorFields(prev => ({ ...prev, rawContent: newContent }));
                          }
                          setEditMode('structured');
                        }}
                      >
                        Structured
                      </button>
                      <button
                        type="button"
                        className={`template-mode-button ${editMode === 'raw' ? 'active' : ''}`}
                        onClick={() => {
                          // Ensure rawContent is up to date when switching to raw mode
                          if (editMode === 'structured') {
                            const newContent = assembleContentFromFields(editorFields);
                            setEditorFields(prev => ({ ...prev, rawContent: newContent }));
                          }
                          setEditMode('raw');
                        }}
                      >
                        Raw
                      </button>
                    </div>
                    {!isReadme(selectedPromptName) && (
                      <>
                        <button
                          type="button"
                          className="template-button"
                          onClick={handleStructurePrompt}
                          disabled={isSaving}
                          title="Auto-structure prompt"
                        >
                          <span className="material-symbols-outlined">auto_fix_high</span>
                          Structure
                        </button>
                        <button
                          type="button"
                          className="template-button primary"
                          onClick={handleSave}
                          disabled={isSaving || isLoadingContent || !isDirty}
                        >
                          {isSaving ? 'Saving...' : 'Save'}
                        </button>
                      </>
                    )}
                    {isReadme(selectedPromptName) && (
                      <div className="template-readme-notice">
                        README is read-only
                      </div>
                    )}
                  </div>
                )}
              </div>

              {error && <div className="template-error">Error: {error}</div>}

              {/* Intelligent hints - real-time warnings */}
              {!isReadme(selectedPromptName) && linterWarnings.length > 0 && (
                <div className="template-intelligent-hints">
                  <div className="template-intelligent-hints-header">
                    <span className="material-symbols-outlined">lightbulb</span>
                    <span>Intelligent Hints</span>
                  </div>
                  <div className="template-intelligent-hints-list">
                    {linterWarnings.slice(0, 3).map((warning, index) => (
                      <div key={index} className={`template-intelligent-hint template-intelligent-hint-${warning.severity}`}>
                        <span className="material-symbols-outlined">
                          {warning.severity === 'warning' ? 'warning' : 'info'}
                        </span>
                        <span>{warning.message}</span>
                      </div>
                    ))}
                    {linterWarnings.length > 3 && (
                      <button
                        type="button"
                        className="template-button ghost"
                        onClick={() => {
                          setHelpModalTab('linter');
                          setShowHelpModal(true);
                        }}
                        style={{ fontSize: '0.875rem', padding: '4px 8px' }}
                      >
                        View all {linterWarnings.length} issues
                      </button>
                    )}
                  </div>
                </div>
              )}

              {isLoadingContent ? (
                <div className="loading">Loading template content...</div>
              ) : isReadme(selectedPromptName) ? (
                <div className="template-editor-form template-readme-view">
                  <div className="template-field body-field">
                    <label>Content (Read-only)</label>
                    <div className="template-readme-content">
                      <pre>{editorFields.rawContent || editorFields.body || 'No content'}</pre>
                    </div>
                  </div>
                </div>
              ) : editMode === 'structured' ? (
                <div className="template-editor-form">
                  <div className="template-field">
                    <label>Title</label>
                    <input
                      type="text"
                      value={editorFields.title}
                      onChange={(e) => handleFieldChange('title', e.target.value)}
                      placeholder="Template title (optional)"
                    />
                  </div>
                  <div className="template-field">
                    <label>Description</label>
                    <textarea
                      value={editorFields.description}
                      onChange={(e) => handleFieldChange('description', e.target.value)}
                      placeholder="Brief description (optional)"
                      rows="2"
                    />
                  </div>
                  <div className="template-field body-field">
                    <label>Body</label>
                    <textarea
                      value={editorFields.body}
                      onChange={(e) => handleFieldChange('body', e.target.value)}
                      placeholder="Template content (Markdown)"
                    />
                  </div>
                </div>
              ) : (
                <div className="template-editor-form">
                  <div className="template-field body-field">
                    <label>Raw Markdown</label>
                    <textarea
                      value={editorFields.rawContent}
                      onChange={(e) => handleRawContentChange(e.target.value)}
                      placeholder="Template content (Markdown)"
                      className="template-raw-textarea"
                    />
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="template-editor-empty">
              <p>
                {viewMode === 'templates' 
                  ? 'Select a template from the list to edit, or click "New" to create one'
                  : 'Select an item from trash to edit or restore'}
              </p>
            </div>
          )}
        </div>
      </div>

      {showHelpModal && (
        <div className="template-help-modal-overlay" onClick={() => setShowHelpModal(false)}>
          <div className="template-help-modal" onClick={(e) => e.stopPropagation()}>
            <div className="template-help-modal-header">
              <h2>Prompt Assistant</h2>
              <button
                type="button"
                className="template-help-modal-close"
                onClick={() => setShowHelpModal(false)}
                title="Close"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="template-help-modal-tabs">
              <button
                type="button"
                className={`template-help-tab ${helpModalTab === 'tips' ? 'active' : ''}`}
                onClick={() => setHelpModalTab('tips')}
              >
                Tips
              </button>
              <button
                type="button"
                className={`template-help-tab ${helpModalTab === 'linter' ? 'active' : ''}`}
                onClick={() => {
                  const currentText = editMode === 'raw' 
                    ? editorFields.rawContent 
                    : assembleContent();
                  const warnings = runPromptLinter(currentText);
                  setLinterWarnings(warnings);
                  setHelpModalTab('linter');
                }}
              >
                Linter
                {linterWarnings.length > 0 && (
                  <span className="template-help-tab-badge">{linterWarnings.length}</span>
                )}
              </button>
              <button
                type="button"
                className={`template-help-tab ${helpModalTab === 'structure' ? 'active' : ''}`}
                onClick={() => setHelpModalTab('structure')}
              >
                Structure
              </button>
            </div>
            <div className="template-help-modal-content">
              {helpModalTab === 'tips' && (
                <div className="template-help-tips-section">
                  <h3>Top 20 Tips for Writing Effective Prompts</h3>
                  <ol className="template-help-tips-list">
                    {promptTips.map((tip, index) => (
                      <li key={index} className="template-help-tip">
                        {tip}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {helpModalTab === 'linter' && (
                <div className="template-help-linter-section">
                  <h3>Prompt Quality Check</h3>
                  <p className="template-help-linter-description">
                    Analyzing your current prompt for missing elements...
                  </p>
                  {linterWarnings.length === 0 ? (
                    <div className="template-help-linter-success">
                      <span className="material-symbols-outlined">check_circle</span>
                      <p>Great! Your prompt looks well-structured.</p>
                    </div>
                  ) : (
                    <div className="template-help-linter-warnings">
                      {linterWarnings.map((warning, index) => (
                        <div key={index} className={`template-help-linter-warning template-help-linter-${warning.severity}`}>
                          <span className="material-symbols-outlined">
                            {warning.severity === 'warning' ? 'warning' : 'info'}
                          </span>
                          <div className="template-help-linter-warning-content">
                            <strong>{warning.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</strong>
                            <p>{warning.message}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    className="template-button primary"
                    onClick={handleLintPrompt}
                    style={{ marginTop: 'var(--md-sys-spacing-md)' }}
                  >
                    <span className="material-symbols-outlined">refresh</span>
                    Re-check Prompt
                  </button>
                </div>
              )}
              {helpModalTab === 'structure' && (
                <div className="template-help-structure-section">
                  <h3>Auto-Structure Prompt</h3>
                  <p className="template-help-structure-description">
                    Automatically organize your prompt into structured sections: Context, Constraints, Architecture, and Expected Output.
                  </p>
                  <div className="template-help-structure-preview">
                    <h4>Preview:</h4>
                    <pre className="template-help-structure-preview-text">
                      {structurePrompt(editMode === 'raw' ? editorFields.rawContent : assembleContent())}
                    </pre>
                  </div>
                  <button
                    type="button"
                    className="template-button primary"
                    onClick={() => {
                      handleStructurePrompt();
                      setShowHelpModal(false);
                    }}
                    style={{ marginTop: 'var(--md-sys-spacing-md)' }}
                  >
                    <span className="material-symbols-outlined">auto_fix_high</span>
                    Apply Structure
                  </button>
                </div>
              )}
            </div>
            <div className="template-help-modal-footer">
              <button
                type="button"
                className="template-button primary"
                onClick={() => setShowHelpModal(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default TemplateEditorTab;

