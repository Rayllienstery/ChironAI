"""Generate llmProxyBuildsTab/ modules from LlmProxyBuildsTab.jsx."""
from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "components"
OUT = SRC / "llmProxyBuildsTab"
OUT.mkdir(parents=True, exist_ok=True)
lines = (SRC / "LlmProxyBuildsTab.jsx").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content.splitlines())} lines")


# --- constants.js ---
c = sl(22, 101)
c = c.replace("const SECTION_TABS", "export const SECTION_TABS", 1)
c = c.replace("const WIZARD_STEPS", "export const WIZARD_STEPS", 1)
c = c.replace("const PARAMETER_PREFABS", "export const PARAMETER_PREFABS", 1)
c = c.replace("const CUSTOM_PARAMETER_PREFAB_NOTE", "export const CUSTOM_PARAMETER_PREFAB_NOTE", 1)
w("constants.js", c)

# --- helpers.js ---
helpers = (
    "import { mergePipelineSnapshot } from '../../hooks/useMergedPipelinePreview';\n"
    "import { CUSTOM_PARAMETER_PREFAB_NOTE, PARAMETER_PREFABS } from './constants';\n\n"
)
h = sl(27, 218)
h = h.replace("function mergeBuildDraftIntoPipelinePreview", "export function mergeBuildDraftIntoPipelinePreview", 1)
h = h.replace("function getMatchingParameterPrefab", "export function getMatchingParameterPrefab", 1)
h = h.replace("function emptyDraft", "export function emptyDraft", 1)
h = h.replace("function buildToDraft", "export function buildToDraft", 1)
h = h.replace("function draftToPayload", "export function draftToPayload", 1)
w("helpers.js", helpers + h)

# --- useLlmProxyBuildsTab.js ---
use_hook = textwrap.dedent(
    """\
    import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
    import {
      getLlmProxyBuilds,
      getModelSettings,
      getPipelinePreview,
      getPrompts,
      getProviderCatalog,
      getRagModelSettings,
      previewLlmProxyBuildModel,
      putLlmProxyBuilds,
    } from '../../services/api';
    import { getMatchingParameterPrefab } from './helpers';
    import { buildToDraft, draftToPayload, emptyDraft } from './helpers';

    export function useLlmProxyBuildsTab({ focusSubTab, onFocusSubTabConsumed }) {
    """
)
use_hook += sl(221, 573)
use_hook += textwrap.dedent(
    """
      return {
        sectionTab,
        setSectionTab,
        builds,
        urls,
        loading,
        err,
        saving,
        providerCatalog,
        prompts,
        proxyDefaults,
        draft,
        setDraft,
        editingId,
        detailId,
        setDetailId,
        detailModalBuild,
        setDetailModalBuild,
        previewBusy,
        previewMsg,
        buildModalPipelineSnap,
        buildModalHybrid,
        buildModalRerank,
        openMenuModel,
        setOpenMenuModel,
        modelMenuRootRef,
        rowBusy,
        wizardStep,
        setWizardStep,
        wizardDirection,
        setWizardDirection,
        chatProviders,
        load,
        loadEditorDependencies,
        buildModalOpen,
        buildModalPipelineData,
        filteredModels,
        isFormValid,
        detailBuild,
        matchingParameterPrefab: getMatchingParameterPrefab(draft),
        applyParameterPrefab,
        openNew,
        openEdit,
        openDetails,
        closeForm,
        closeDetails,
        openDetailModal,
        closeDetailModal,
        saveForm,
        deleteBuild,
        runPreview,
        applySelectedModelDefaults,
      };
    }
    """
)
w("useLlmProxyBuildsTab.js", use_hook)

# --- LlmProxyBuildsListPanel.jsx ---
list_panel = textwrap.dedent(
    """\
    import React from 'react';
    import CoreUIButton from '../CoreUIButton';
    import CoreUIModal from '../CoreUIModal';

    export default function LlmProxyBuildsListPanel({
      urls,
      err,
      saving,
      load,
      openNew,
      draft,
      builds,
      rowBusy,
      detailId,
      openDetails,
      openEdit,
      openDetailModal,
      deleteBuild,
      setOpenMenuModel,
      openMenuModel,
      modelMenuRootRef,
      detailModalBuild,
      closeDetailModal,
    }) {
      return (
        <>
    """
) + sl(601, 889) + "\n    </>\n  );\n}\n"
w("LlmProxyBuildsListPanel.jsx", list_panel)

# --- LlmProxyWizardSteps.jsx ---
wizard_steps = textwrap.dedent(
    """\
    import React from 'react';
    import { CUSTOM_PARAMETER_PREFAB_NOTE } from './constants';

    export default function LlmProxyWizardSteps({
      wizardStep,
      draft,
      setDraft,
      editingId,
      chatProviders,
      filteredModels,
      previewBusy,
      previewMsg,
      runPreview,
      applySelectedModelDefaults,
      parameterPrefabNote,
      applyParameterPrefab,
      buildModalPipelineData,
      buildModalHybrid,
      buildModalRerank,
      proxyDefaults,
    }) {
      return (
    """
) + sl(959, 1699) + "\n  );\n}\n"
wizard_steps = wizard_steps.replace(
    "const parameterPrefabNote = matchingParameterPrefab || CUSTOM_PARAMETER_PREFAB_NOTE;",
    "/* parameterPrefabNote passed as prop */",
)
w("LlmProxyWizardSteps.jsx", wizard_steps)

# --- LlmProxyBuildWizardModal.jsx ---
wizard_modal = textwrap.dedent(
    """\
    import React from 'react';
    import CoreUIButton from '../CoreUIButton';
    import CoreUIModal from '../CoreUIModal';
    import { WIZARD_STEPS } from './constants';
    import LlmProxyWizardSteps from './LlmProxyWizardSteps';

    export default function LlmProxyBuildWizardModal({
      draft,
      editingId,
      closeForm,
      wizardStep,
      setWizardStep,
      wizardDirection,
      setWizardDirection,
      saving,
      saveForm,
      chatProviders,
      filteredModels,
      previewBusy,
      previewMsg,
      runPreview,
      applySelectedModelDefaults,
      parameterPrefabNote,
      applyParameterPrefab,
      buildModalPipelineData,
      buildModalHybrid,
      buildModalRerank,
      proxyDefaults,
      setDraft,
    }) {
      if (!draft) return null;
      return (
    """
) + sl(892, 958) + "\n" + sl(1698, 1702) + "\n      );\n    }\n"
# Fix wizard content to use LlmProxyWizardSteps component
wizard_modal = wizard_modal.replace(
    sl(959, 1699).strip().split("\n")[0],
    "            <LlmProxyWizardSteps",
)
# The above replace won't work well - rebuild wizard modal properly
wizard_modal = textwrap.dedent(
    """\
    import React from 'react';
    import CoreUIButton from '../CoreUIButton';
    import CoreUIModal from '../CoreUIModal';
    import { WIZARD_STEPS } from './constants';
    import LlmProxyWizardSteps from './LlmProxyWizardSteps';

    export default function LlmProxyBuildWizardModal(props) {
      const {
        draft,
        editingId,
        closeForm,
        wizardStep,
        setWizardStep,
        saving,
        saveForm,
      } = props;
      if (!draft) return null;
      return (
    """
) + sl(892, 958)
wizard_modal += textwrap.dedent(
    """
            <LlmProxyWizardSteps {...props} />
    """
)
wizard_modal += sl(1700, 1702) + "\n      );\n    }\n"
w("LlmProxyBuildWizardModal.jsx", wizard_modal)

# --- LlmProxyBuildsTab.jsx ---
container = textwrap.dedent(
    """\
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
    """
)
(SRC / "LlmProxyBuildsTab.jsx").write_text(container, encoding="utf-8")
print(f"LlmProxyBuildsTab.jsx: {len(container.splitlines())} lines")
print("Done.")
