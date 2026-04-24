function TemplateContentForm({
  editMode,
  editorFields,
  handleFieldChange,
  handleRawContentChange,
  bodyRows,
  rawRows,
}) {
  if (editMode === 'structured') {
    return (
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
            rows={bodyRows ? '2' : undefined}
          />
        </div>
        <div className={`template-field${bodyRows ? '' : ' body-field'}`}>
          <label>Body</label>
          <textarea
            value={editorFields.body}
            onChange={(e) => handleFieldChange('body', e.target.value)}
            placeholder="Template content (Markdown)"
            rows={bodyRows || undefined}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="template-editor-form">
      <div className={`template-field${rawRows ? '' : ' body-field'}`}>
        <label>Raw Markdown</label>
        <textarea
          value={editorFields.rawContent}
          onChange={(e) => handleRawContentChange(e.target.value)}
          placeholder="Template content (Markdown)"
          rows={rawRows || undefined}
          className="template-raw-textarea"
        />
      </div>
    </div>
  );
}

function EditModeToggle({ editMode, onStructured, onRaw }) {
  return (
    <div className="template-edit-mode-toggle">
      <button
        type="button"
        className={`template-mode-button ${editMode === 'structured' ? 'active' : ''}`}
        onClick={onStructured}
      >
        Structured
      </button>
      <button
        type="button"
        className={`template-mode-button ${editMode === 'raw' ? 'active' : ''}`}
        onClick={onRaw}
      >
        Raw
      </button>
    </div>
  );
}

export default function TemplateEditorPanel(props) {
  const {
    mode,
    viewMode,
    selectedTrashName,
    trashPrompts,
    selectedPromptName,
    renamePromptName,
    renameValue,
    setRenameValue,
    handleRenameSave,
    handleRenameCancel,
    handleRenameStart,
    newTemplateName,
    setNewTemplateName,
    handleCreateNewSave,
    handleCreateNewCancel,
    setShowHelpModal,
    editMode,
    setEditMode,
    assembleContentFromFields,
    editorFields,
    setEditorFields,
    handleStructurePrompt,
    handleRestore,
    handleSave,
    isSaving,
    isLoadingContent,
    isDirty,
    error,
    handleFieldChange,
    handleRawContentChange,
    isReadme,
    linterWarnings,
    setHelpModalTab,
    handleDuplicate,
    handleDelete,
  } = props;

  const switchToStructured = () => {
    if (editMode === 'raw') {
      const newContent = assembleContentFromFields(editorFields);
      setEditorFields((prev) => ({ ...prev, rawContent: newContent }));
    }
    setEditMode('structured');
  };

  const switchToRaw = () => {
    if (editMode === 'structured') {
      const newContent = assembleContentFromFields(editorFields);
      setEditorFields((prev) => ({ ...prev, rawContent: newContent }));
    }
    setEditMode('raw');
  };

  if (mode === 'trash') {
    return (
      <>
        <div className="template-editor-header">
          <h2>
            <div className="template-name-with-rename">
              <span>
                {trashPrompts.find((p) => p.trash_name === selectedTrashName)?.name ||
                  selectedTrashName}
              </span>
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
            <EditModeToggle
              editMode={editMode}
              onStructured={switchToStructured}
              onRaw={switchToRaw}
            />
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
        ) : (
          <TemplateContentForm
            editMode={editMode}
            editorFields={editorFields}
            handleFieldChange={handleFieldChange}
            handleRawContentChange={handleRawContentChange}
          />
        )}
      </>
    );
  }

  if (mode === 'new') {
    return (
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
            <EditModeToggle
              editMode={editMode}
              onStructured={switchToStructured}
              onRaw={switchToRaw}
            />
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
        <TemplateContentForm
          editMode={editMode}
          editorFields={editorFields}
          handleFieldChange={handleFieldChange}
          handleRawContentChange={handleRawContentChange}
          bodyRows={20}
          rawRows={25}
        />
      </>
    );
  }

  if (mode === 'selected') {
    return (
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
              <EditModeToggle
                editMode={editMode}
                onStructured={switchToStructured}
                onRaw={switchToRaw}
              />
              {!isReadme(selectedPromptName) ? (
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
                    className="template-button"
                    onClick={handleDuplicate}
                    disabled={isSaving}
                    title="Duplicate template"
                  >
                    <span className="material-symbols-outlined">content_copy</span>
                    Duplicate
                  </button>
                  <button
                    type="button"
                    className="template-button delete"
                    onClick={handleDelete}
                    disabled={isSaving}
                    title="Move to trash"
                  >
                    <span className="material-symbols-outlined">delete</span>
                    Delete
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
              ) : (
                <div className="template-readme-notice">README is read-only</div>
              )}
            </div>
          )}
        </div>
        {error && <div className="template-error">Error: {error}</div>}
        {!isReadme(selectedPromptName) && linterWarnings.length > 0 && (
          <div className="template-intelligent-hints">
            <div className="template-intelligent-hints-header">
              <span className="material-symbols-outlined">lightbulb</span>
              <span>Intelligent Hints</span>
            </div>
            <div className="template-intelligent-hints-list">
              {linterWarnings.slice(0, 3).map((warning, index) => (
                <div
                  key={index}
                  className={`template-intelligent-hint template-intelligent-hint-${warning.severity}`}
                >
                  <span className="material-symbols-outlined">
                    {warning.severity === 'warning' ? 'warning' : 'info'}
                  </span>
                  <span>{warning.message}</span>
                </div>
              ))}
              {linterWarnings.length > 3 && (
                <button
                  type="button"
                  className="template-button ghost template-button--compact"
                  onClick={() => {
                    setHelpModalTab('linter');
                    setShowHelpModal(true);
                  }}
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
        ) : (
          <TemplateContentForm
            editMode={editMode}
            editorFields={editorFields}
            handleFieldChange={handleFieldChange}
            handleRawContentChange={handleRawContentChange}
          />
        )}
      </>
    );
  }

  return (
    <div className="template-editor-empty">
      <p>
        {viewMode === 'templates'
          ? 'Select a template from the list to edit, or click "New" to create one'
          : 'Select an item from trash to edit or restore'}
      </p>
    </div>
  );
}
