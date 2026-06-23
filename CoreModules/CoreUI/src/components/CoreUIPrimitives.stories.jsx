import { useState } from 'react';
import CoreUIButton from './CoreUIButton.jsx';
import CoreUIPillTabs from './CoreUIPillTabs.jsx';
import CoreUISubtabs from './CoreUISubtabs.jsx';
import CoreUIModal from './CoreUIModal.jsx';

const primaryTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'retrieval', label: 'Retrieval' },
  { id: 'settings', label: 'Settings' },
];

const secondaryTabs = [
  { id: 'logs', label: 'Logs' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'alerts', label: 'Alerts' },
];

export default {
  title: 'CoreUI/Primitives',
};

export function Buttons() {
  return (
    <div className="coreui-stack-md">
      <CoreUIButton variant="primary">Primary action</CoreUIButton>
      <CoreUIButton>Default action</CoreUIButton>
      <CoreUIButton variant="ghost">Ghost action</CoreUIButton>
      <CoreUIButton variant="danger">Danger action</CoreUIButton>
      <CoreUIButton variant="icon" aria-label="Refresh">
        <span className="material-symbols-outlined" aria-hidden="true">refresh</span>
      </CoreUIButton>
    </div>
  );
}

export function PillTabs() {
  const [value, setValue] = useState('overview');
  return (
    <CoreUIPillTabs
      tabs={primaryTabs}
      value={value}
      onChange={setValue}
      ariaLabel="Primary sections"
    />
  );
}

export function Subtabs() {
  const [value, setValue] = useState('logs');
  return (
    <section className="coreui-card-shell coreui-p-md" aria-label="Panel with subtabs">
      <CoreUISubtabs
        tabs={secondaryTabs}
        value={value}
        onChange={setValue}
        ariaLabel="Panel sections"
      />
    </section>
  );
}

export function Modal() {
  return (
    <CoreUIModal
      title="Review extension action"
      onClose={() => {}}
      footer={<CoreUIButton variant="primary">Confirm</CoreUIButton>}
    >
      <p>Use CoreUIModal for focused confirmation and editing flows.</p>
    </CoreUIModal>
  );
}
