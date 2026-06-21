import { render } from '@testing-library/react';
import axe from 'axe-core';
import { describe, expect, it } from 'vitest';
import CoreUIButton from './CoreUIButton.jsx';
import CoreUIPillTabs from './CoreUIPillTabs.jsx';
import CoreUISubtabs from './CoreUISubtabs.jsx';
import CoreUIModal from './CoreUIModal.jsx';

async function expectNoA11yViolations(container) {
  const results = await axe.run(container, {
    rules: {
      // axe's color-contrast rule requires canvas APIs that jsdom does not implement.
      'color-contrast': { enabled: false },
    },
  });
  expect(results.violations).toEqual([]);
}

describe('CoreUI primitive accessibility', () => {
  it('keeps key tab controls accessible', async () => {
    const { container } = render(
      <main>
        <CoreUIPillTabs
          tabs={[
            { id: 'main', label: 'Main' },
            { id: 'settings', label: 'Settings' },
          ]}
          value="main"
          ariaLabel="RAG sections"
        />
        <section className="coreui-card-shell coreui-p-md" aria-label="Nested panel">
          <CoreUISubtabs
            tabs={[
              { id: 'logs', label: 'Logs' },
              { id: 'metrics', label: 'Metrics' },
            ]}
            value="logs"
            ariaLabel="Panel sections"
          />
        </section>
      </main>,
    );

    await expectNoA11yViolations(container);
  });

  it('keeps modal and button primitives accessible', async () => {
    const { container } = render(
      <CoreUIModal
        title="Confirm action"
        onClose={() => {}}
        footer={<CoreUIButton variant="primary">Confirm</CoreUIButton>}
      >
        <p>Confirm the selected operation before continuing.</p>
      </CoreUIModal>,
    );

    await expectNoA11yViolations(container);
  });
});
