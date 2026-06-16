import React from 'react';
import Card from '../Card';

export default function RagKeywordsSheets({
  sheetOpen,
  setSheetOpen,
  keywordCollections,
  savingKeywords,
  handleAddCollection,
  editCollectionId,
  editDraft,
  setEditDraft,
  handleToggleEnabled,
  handleSaveEdit,
  handleCancelEdit,
  handleStartEdit,
  handleOpenAddWords,
  handlePasteIntoCollection,
  deleteConfirmId,
  setDeleteConfirmId,
  handleDeleteCollection,
  addWordsCollectionId,
  setAddWordsCollectionId,
  addWordsInput,
  setAddWordsInput,
  addWordsList,
  handleAddWordInputKeyDown,
  handleAddWordsSave,
}) {
  return (
    <>
      {sheetOpen && (
        <div className="rag-sheet-overlay" onClick={() => setSheetOpen(false)}>
          <Card
            className="rag-sheet"
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            elevation="var(--md-sys-elevation-level3)"
          >
            <div className="rag-sheet-header">
              <h3>Keywords that trigger RAG search</h3>
              <button type="button" className="rag-sheet-close" onClick={() => setSheetOpen(false)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="rag-sheet-body">
              <div className="rag-sheet-actions">
                <button
                  type="button"
                  className="rag-button primary"
                  disabled={savingKeywords}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAddCollection();
                  }}
                >
                  Add collection
                </button>
              </div>
              {keywordCollections.length === 0 ? (
                <div className="empty-state">No keyword collections. Add one to define trigger words.</div>
              ) : (
                <div className="rag-keyword-collections-list">
                  {keywordCollections.map((coll) => {
                    const isEditing = editCollectionId === coll.id;
                    const draft = isEditing ? editDraft : null;
                    return (
                      <div key={coll.id} className="rag-keyword-collection-block">
                        <div className="rag-keyword-collection-header">
                          <label className="rag-keyword-collection-toggle">
                            <input
                              type="checkbox"
                              checked={!!coll.enabled}
                              onChange={() => handleToggleEnabled(coll)}
                            />
                            <span>Enabled</span>
                          </label>
                          {isEditing ? (
                            <input
                              type="text"
                              className="rag-keyword-collection-name-input"
                              value={draft?.name ?? ''}
                              onChange={(e) => setEditDraft((d) => (d ? { ...d, name: e.target.value } : null))}
                              placeholder="Collection name"
                            />
                          ) : (
                            <span className="rag-keyword-collection-name">{coll.name}</span>
                          )}
                          <div className="rag-keyword-collection-buttons">
                            {isEditing ? (
                              <>
                                <button type="button" className="rag-button" onClick={handleSaveEdit} disabled={savingKeywords}>
                                  Save
                                </button>
                                <button type="button" className="rag-button ghost" onClick={handleCancelEdit}>
                                  Cancel
                                </button>
                              </>
                            ) : (
                              <>
                                <button type="button" className="rag-button ghost" onClick={() => handleStartEdit(coll)}>
                                  Edit
                                </button>
                                <button type="button" className="rag-button ghost" onClick={() => handleOpenAddWords(coll)}>
                                  Add
                                </button>
                                <button type="button" className="rag-button ghost" onClick={() => handlePasteIntoCollection(coll)}>
                                  Paste
                                </button>
                                {deleteConfirmId === coll.id ? (
                                  <>
                                    <span className="rag-delete-confirm-text">Delete?</span>
                                    <button type="button" className="rag-button" onClick={() => handleDeleteCollection(coll.id)}>
                                      Yes
                                    </button>
                                    <button type="button" className="rag-button ghost" onClick={() => setDeleteConfirmId(null)}>
                                      No
                                    </button>
                                  </>
                                ) : (
                                  <button type="button" className="rag-button ghost" onClick={() => setDeleteConfirmId(coll.id)}>
                                    Delete
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                        <div className="rag-keyword-collection-keywords">
                          {isEditing && draft ? (
                            <div className="rag-keywords-edit-list">
                              {draft.keywords.map((kw, idx) => (
                                <div key={idx} className="rag-keyword-edit-row">
                                  <input
                                    type="text"
                                    value={kw}
                                    onChange={(e) => {
                                      const next = [...draft.keywords];
                                      next[idx] = e.target.value;
                                      setEditDraft((d) => (d ? { ...d, keywords: next } : null));
                                    }}
                                  />
                                  <button
                                    type="button"
                                    className="rag-button ghost"
                                    onClick={() => {
                                      const next = draft.keywords.filter((_, i) => i !== idx);
                                      setEditDraft((d) => (d ? { ...d, keywords: next } : null));
                                    }}
                                  >
                                    Remove
                                  </button>
                                </div>
                              ))}
                              <button
                                type="button"
                                className="rag-button ghost"
                                onClick={() => setEditDraft((d) => (d ? { ...d, keywords: [...d.keywords, ''] } : null))}
                              >
                                + Add word
                              </button>
                            </div>
                          ) : (
                            <div className="rag-keywords-chips">
                              {(coll.keywords || []).map((kw, idx) => (
                                <span key={idx} className="rag-keyword-chip">
                                  {kw}
                                </span>
                              ))}
                              {(coll.keywords || []).length === 0 && (
                                <span className="rag-keywords-empty">No keywords</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="rag-sheet-footer">
              <button type="button" className="rag-button" onClick={() => setSheetOpen(false)}>
                Close
              </button>
            </div>
          </Card>
        </div>
      )}

      {addWordsCollectionId && (
        <div className="rag-sheet-overlay" onClick={() => setAddWordsCollectionId(null)}>
          <div className="rag-sheet rag-add-words-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="rag-sheet-header">
              <h3>Add words</h3>
              <button type="button" className="rag-sheet-close" onClick={() => setAddWordsCollectionId(null)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="rag-sheet-body">
              <p className="rag-add-words-hint">Type a word and press Enter to add. Preview below.</p>
              <input
                type="text"
                className="rag-add-words-input"
                value={addWordsInput}
                onChange={(e) => setAddWordsInput(e.target.value)}
                onKeyDown={handleAddWordInputKeyDown}
                placeholder="Type word and press Enter"
                autoFocus
              />
              <div className="rag-add-words-preview">
                {addWordsList.length === 0 ? '—' : addWordsList.join(', ')}
              </div>
            </div>
            <div className="rag-sheet-footer">
              <button type="button" className="rag-button ghost" onClick={() => setAddWordsCollectionId(null)}>
                Cancel
              </button>
              <button type="button" className="rag-button primary" onClick={handleAddWordsSave} disabled={savingKeywords}>
                Save
              </button>
            </div>
          </div>
        </div>
      )}

    </>
  );
}
