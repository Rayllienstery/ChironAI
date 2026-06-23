import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import SwaggerTab from './SwaggerTab.jsx';

describe('SwaggerTab smoke', () => {
  it('renders heading and OpenAPI JSON link', () => {
    render(<SwaggerTab />);
    expect(screen.getByRole('heading', { level: 2, name: /Swagger/i })).toBeInTheDocument();
    const specLink = screen.getByRole('link', { name: /OpenAPI JSON/i });
    expect(specLink).toHaveAttribute('href', '/api/webui/openapi.json');
  });

  it('shows loading status until iframe loads', () => {
    render(<SwaggerTab />);
    expect(screen.getByRole('status')).toHaveTextContent(/Loading Swagger UI/i);
    fireEvent.load(screen.getByTitle('ChironAI Swagger UI'));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
