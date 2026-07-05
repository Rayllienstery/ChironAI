import React from 'react';
import LlmProxyAutocompletePanel from './LlmProxyAutocompletePanel';
import CoreUIPillTabs from './CoreUIPillTabs';
import '../styles/components/DashboardTab.css';
import '../styles/components/SettingsTab.css';
import '../styles/components/LlmProxyTab.css';
import { SECTION_TABS } from './llmProxyBuildsTab/constants';
import { CUSTOM_PARAMETER_PREFAB_NOTE } from './llmProxyBuildsTab/constants';
import LlmProxyBuildWizardModal from './llmProxyBuildsTab/LlmProxyBuildWizardModal';
import LlmProxyBuildsListPanel from './llmProxyBuildsTab/LlmProxyBuildsListPanel';
import { useLlmProxyBuildsTab } from './llmProxyBuildsTab/useLlmProxyBuildsTab';

function LlmProxyBuildsTab({ focusSubTab, onFocusSubTabConsumed }) {
  const tab = useLlmProxyBuildsTab({ focusSubTab, onFocusSubTabConsumed });
  const parameterPrefabNote = tab.matchingParameterPrefab || CUSTOM_PARAMETER_PREFAB_NOTE;

  if (tab.loading) {
    return (
      <div className="settings-tab settings-tab--fullwidth llm-proxy-tab tab-view">
        <p className="settings-intro">Loading builds…</p>
      </div>
    );
  }

  return (
    <div className="settings-tab settings-tab--fullwidth llm-proxy-tab tab-view">
      <div className="llm-proxy-header">
        <div className="llm-proxy-header-row">
          <h2>LLM Proxy</h2>
        </div>
        <CoreUIPillTabs
          tabs={SECTION_TABS}
          value={tab.sectionTab}
          onChange={tab.setSectionTab}
          ariaLabel="LLM Proxy sections"
        />
      </div>

      {tab.sectionTab === 'autocomplete' && <LlmProxyAutocompletePanel />}

      {tab.sectionTab === 'builds' && (
        <>
          <LlmProxyBuildsListPanel
            urls={tab.urls}
            err={tab.err}
            saving={tab.saving}
            load={tab.load}
            openNew={tab.openNew}
            draft={tab.draft}
            builds={tab.builds}
            rowBusy={tab.rowBusy}
            detailId={tab.detailId}
            openDetails={tab.openDetails}
            closeDetails={tab.closeDetails}
            openEdit={tab.openEdit}
            openDetailModal={tab.openDetailModal}
            deleteBuild={tab.deleteBuild}
            setOpenMenuModel={tab.setOpenMenuModel}
            openMenuModel={tab.openMenuModel}
            modelMenuRootRef={tab.modelMenuRootRef}
            detailModalBuild={tab.detailModalBuild}
            closeDetailModal={tab.closeDetailModal}
          />
          <LlmProxyBuildWizardModal
            draft={tab.draft}
            editingId={tab.editingId}
            closeForm={tab.closeForm}
            wizardStep={tab.wizardStep}
            setWizardStep={tab.setWizardStep}
            wizardDirection={tab.wizardDirection}
            setWizardDirection={tab.setWizardDirection}
            saving={tab.saving}
            saveForm={tab.saveForm}
            setDraft={tab.setDraft}
            chatProviders={tab.chatProviders}
            filteredModels={tab.filteredModels}
            previewBusy={tab.previewBusy}
            previewMsg={tab.previewMsg}
            runPreview={tab.runPreview}
            applySelectedModelDefaults={tab.applySelectedModelDefaults}
            parameterPrefabNote={parameterPrefabNote}
            applyParameterPrefab={tab.applyParameterPrefab}
            prompts={tab.prompts}
            ragCollections={tab.ragCollections}
            matchingParameterPrefab={tab.matchingParameterPrefab}
            buildModalPipelineData={tab.buildModalPipelineData}
            buildModalHybrid={tab.buildModalHybrid}
            buildModalRerank={tab.buildModalRerank}
            proxyDefaults={tab.proxyDefaults}
          />
        </>
      )}
    </div>
  );
}

export default LlmProxyBuildsTab;
