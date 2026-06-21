import '../src/styles/tokens.css';
import '../src/styles/coreui-system.css';
import '../src/styles/layout.css';
import '../src/styles/default-card.css';
import '../src/styles/components/CoreUIButtons.css';
import '../src/styles/components/CoreUIPillTabs.css';
import '../src/styles/components/CoreUISubtabs.css';

/** @type { import('@storybook/react').Preview } */
const preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
