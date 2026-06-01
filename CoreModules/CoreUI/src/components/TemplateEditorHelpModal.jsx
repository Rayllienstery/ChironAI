/**
 * Modal that surfaces tips, an in-place prompt linter, and an auto-structure preview
 * for the Prompt Template Editor.
 *
 * @param {Object} props
 * @param {boolean} props.open - Whether the modal is visible.
 * @param {Function} props.onClose - Close handler.
 * @param {'tips'|'linter'|'structure'} props.helpModalTab - Active tab id.
 * @param {Function} props.setHelpModalTab - Setter for the active tab.
 * @param {Array} props.linterWarnings - Linter warnings for the current prompt.
 * @param {Function} props.setLinterWarnings - Setter for linter warnings.
 * @param {string[]} props.promptTips - Tips list.
 * @param {'raw'|'structured'} props.editMode - Editor mode.
 * @param {Object} props.editorFields - Editor raw/structured fields.
 * @param {Function} props.assembleContent - Build the current content from editor fields.
 * @param {Function} props.runPromptLinter - Run linter on the given content.
 * @param {Function} props.structurePrompt - Generate structured prompt preview.
 * @param {Function} props.handleLintPrompt - Re-run linter and apply results.
 * @param {Function} props.handleStructurePrompt - Apply structured prompt.
 */
export default function TemplateEditorHelpModal({
  open,
  onClose,
  helpModalTab,
  setHelpModalTab,
  linterWarnings,
  setLinterWarnings,
  promptTips,
  editMode,
  editorFields,
  assembleContent,
  runPromptLinter,
  structurePrompt,
  handleLintPrompt,
  handleStructurePrompt,
}) {
  if (!open) return null;

  return (
    <div className="template-help-modal-overlay" onClick={onClose}>
      <div className="template-help-modal" onClick={(e) => e.stopPropagation()}>
        <div className="template-help-modal-header">
          <h2>Prompt Assistant</h2>
          <button
            type="button"
            className="template-help-modal-close"
            onClick={onClose}
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
              const currentText =
                editMode === 'raw' ? editorFields.rawContent : assembleContent();
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
                    <div
                      key={index}
                      className={`template-help-linter-warning template-help-linter-${warning.severity}`}
                    >
                      <span className="material-symbols-outlined">
                        {warning.severity === 'warning' ? 'warning' : 'info'}
                      </span>
                      <div className="template-help-linter-warning-content">
                        <strong>
                          {warning.type
                            .replace(/_/g, ' ')
                            .replace(/\b\w/g, (l) => l.toUpperCase())}
                        </strong>
                        <p>{warning.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <button
                type="button"
                className="template-button primary coreui-mt-md"
                onClick={handleLintPrompt}
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
                Automatically organize your prompt into structured sections:
                Context, Constraints, Architecture, and Expected Output.
              </p>
              <div className="template-help-structure-preview">
                <h4>Preview:</h4>
                <pre className="template-help-structure-preview-text">
                  {structurePrompt(
                    editMode === 'raw' ? editorFields.rawContent : assembleContent(),
                  )}
                </pre>
              </div>
              <button
                type="button"
                className="template-button primary coreui-mt-md"
                onClick={() => {
                  handleStructurePrompt();
                  onClose();
                }}
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
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
