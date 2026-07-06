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
    setWizardDirection,
    saving,
    saveForm,
  } = props;
  if (!draft) return null;
  return (
    <CoreUIModal
      title={editingId ? `Edit build: ${editingId}` : 'Create new build'}
      onClose={closeForm}
      className="llm-proxy-build-modal"
      footer={
        <div className="llm-proxy-wizard-nav">
          <div className="llm-proxy-wizard-nav-left">
            {wizardStep > 0 && (
              <CoreUIButton
                variant="primary"
                onClick={() => {
                  setWizardStep(wizardStep - 1);
                  setWizardDirection('back');
                }}
              >
                <span className="material-symbols-outlined coreui-icon--sm" aria-hidden="true">arrow_back</span>
                Back
              </CoreUIButton>
            )}
          </div>
          <div className="llm-proxy-wizard-nav-center">
            <CoreUIButton variant="primary" disabled={saving} onClick={saveForm} data-tour="build-wizard-save">
              <span className="material-symbols-outlined coreui-icon--sm" aria-hidden="true">save</span>
              {saving ? 'Saving...' : 'Save build'}
            </CoreUIButton>
          </div>
          <div className="llm-proxy-wizard-nav-right">
            {wizardStep < WIZARD_STEPS.length - 1 && (
              <CoreUIButton
                variant="primary"
                onClick={() => {
                  setWizardStep(wizardStep + 1);
                  setWizardDirection('forward');
                }}
              >
                Next
                <span className="material-symbols-outlined coreui-icon--sm" aria-hidden="true">arrow_forward</span>
              </CoreUIButton>
            )}
          </div>
        </div>
      }
    >
      <div className="llm-proxy-wizard-steps" role="tablist" aria-label="Build configuration sections">
        {WIZARD_STEPS.map((step, idx) => (
          <button
            key={step.id}
            type="button"
            role="tab"
            aria-selected={idx === wizardStep}
            className={`llm-proxy-wizard-step${
              idx === wizardStep ? ' llm-proxy-wizard-step-active' : ''
            }${idx < wizardStep ? ' llm-proxy-wizard-step-completed' : ''}`}
            onClick={() => {
              setWizardStep(idx);
              setWizardDirection(idx < wizardStep ? 'back' : 'forward');
            }}
            data-step={idx + 1}
            aria-label={`Step ${idx + 1}: ${step.label}`}
            aria-current={idx === wizardStep ? 'step' : undefined}
          >
            <span className="llm-proxy-wizard-step-icon material-symbols-outlined" aria-hidden="true">
              {idx < wizardStep ? 'check' : step.icon}
            </span>
            {step.label}
          </button>
        ))}
      </div>
      <div className="llm-proxy-wizard-content-wrapper" data-tour="build-wizard">
        <LlmProxyWizardSteps {...props} />
      </div>
    </CoreUIModal>
  );
}
