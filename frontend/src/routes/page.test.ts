import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Page from './+page.svelte';
import type { HealthState } from '$lib/health';

vi.mock('$app/navigation', () => ({ invalidate: vi.fn() }));

afterEach(cleanup);

const operational: HealthState = {
	apiReachable: true,
	database: 'ok',
	degraded: false,
	apiBaseUrl: 'http://127.0.0.1:8000',
	detail: null
};

const degraded: HealthState = {
	apiReachable: false,
	database: 'unknown',
	degraded: true,
	apiBaseUrl: 'http://127.0.0.1:8000',
	detail: 'Backend did not answer'
};

describe('+page.svelte', () => {
	it('renders the operational status card', () => {
		render(Page, { data: { health: operational } });

		expect(screen.getByText('operational')).toBeInTheDocument();
		expect(screen.getByText('connected')).toBeInTheDocument();
		expect(screen.getByText('ok')).toBeInTheDocument();
		expect(screen.queryByText('Backend did not answer')).not.toBeInTheDocument();
	});

	it('renders the degraded status card with detail and base URL', () => {
		render(Page, { data: { health: degraded } });

		expect(screen.getByText('degraded')).toBeInTheDocument();
		expect(screen.getByText('unreachable')).toBeInTheDocument();
		expect(screen.getByText('unknown')).toBeInTheDocument();
		expect(screen.getByText('Backend did not answer')).toBeInTheDocument();
		expect(screen.getByText('http://127.0.0.1:8000')).toBeInTheDocument();
	});

	it('offers a refresh button', () => {
		render(Page, { data: { health: operational } });

		expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled();
	});
});
