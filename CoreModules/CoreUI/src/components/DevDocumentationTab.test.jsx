import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DevDocumentationTab from './DevDocumentationTab.jsx';

describe('DevDocumentationTab', () => {
  it('renders the developer documentation overview and switches sections', () => {
    render(<DevDocumentationTab />);

    expect(screen.getByRole('heading', { name: 'Dev Documentation' })).toBeInTheDocument();
    expect(screen.getByText(/create_provider\(host_context, manifest\)/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /architecture/i }));

    expect(screen.getByRole('heading', { name: 'Architecture Overview' })).toBeInTheDocument();
  });
});
