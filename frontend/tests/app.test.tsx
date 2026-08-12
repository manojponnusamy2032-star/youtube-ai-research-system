import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

// Mock the dashboard hooks to avoid real API/React Query usage
vi.mock('../hooks/useDashboard', () => ({
  useMetrics: () => ({ data: {}, isLoading: false, error: null }),
  useRecentWorkflows: () => ({ data: [], isLoading: false, error: null }),
  useRecentContent: () => ({ data: [], isLoading: false, error: null }),
  useLatestVideos: () => ({ data: [], isLoading: false, error: null }),
}));

// Import the page after mocking
import Page from '../app/page';

describe('Dashboard page', () => {
  it('renders without runtime error and shows heading', () => {
    const html = renderToString(React.createElement(Page));
    expect(html).toContain('Dashboard');
  });
});
