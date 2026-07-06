import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

vi.mock('../components/onboarding/useContextualTour.js', () => ({
  useContextualTour: vi.fn(),
}));
