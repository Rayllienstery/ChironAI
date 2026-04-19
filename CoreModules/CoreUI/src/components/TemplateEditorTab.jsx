import { useState, useEffect } from 'react';
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
import TemplateEditorHelpModal from './TemplateEditorHelpModal';
import TemplateEditorPanel from './TemplateEditorPanel';
import '../styles/components/TemplateEditorTab.css';

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
                  )}
                  {readmePrompts.length > 0 && regularPrompts.length > 0 && (
                    <div style={{ height: 'var(--md-sys-spacing-lg)' }} />
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
          <TemplateEditorPanel
            mode={viewMode === 'trash' && selectedTrashName ? 'trash' : isCreatingNew ? 'new' : viewMode === 'templates' && selectedPromptName ? 'selected' : 'empty'}
            viewMode={viewMode}
            selectedTrashName={selectedTrashName}
            trashPrompts={trashPrompts}
            selectedPromptName={selectedPromptName}
            renamePromptName={renamePromptName}
            renameValue={renameValue}
            setRenameValue={setRenameValue}
            handleRenameSave={handleRenameSave}
            handleRenameCancel={handleRenameCancel}
            handleRenameStart={handleRenameStart}
            newTemplateName={newTemplateName}
            setNewTemplateName={setNewTemplateName}
            handleCreateNewSave={handleCreateNewSave}
            handleCreateNewCancel={handleCreateNewCancel}
            setShowHelpModal={setShowHelpModal}
            editMode={editMode}
            setEditMode={setEditMode}
            assembleContentFromFields={assembleContentFromFields}
            editorFields={editorFields}
            setEditorFields={setEditorFields}
            handleStructurePrompt={handleStructurePrompt}
            handleRestore={handleRestore}
            handleSave={handleSave}
            isSaving={isSaving}
            isLoadingContent={isLoadingContent}
            isDirty={isDirty}
            error={error}
            handleFieldChange={handleFieldChange}
            handleRawContentChange={handleRawContentChange}
            isReadme={isReadme}
            linterWarnings={linterWarnings}
            setHelpModalTab={setHelpModalTab}
            handleDuplicate={handleDuplicate}
            handleDelete={handleDelete}
          />
        </div>

      </div>

      <TemplateEditorHelpModal
        open={showHelpModal}
        onClose={() => setShowHelpModal(false)}
        helpModalTab={helpModalTab}
        setHelpModalTab={setHelpModalTab}
        linterWarnings={linterWarnings}
        setLinterWarnings={setLinterWarnings}
        promptTips={promptTips}
        editMode={editMode}
        editorFields={editorFields}
        assembleContent={assembleContent}
        runPromptLinter={runPromptLinter}
        structurePrompt={structurePrompt}
        handleLintPrompt={handleLintPrompt}
        handleStructurePrompt={handleStructurePrompt}
      />
    </div>
  );
}

export default TemplateEditorTab;
