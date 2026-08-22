import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Page from './+page.svelte';
import type { Campaign } from '$lib/campaigns';

vi.mock('$app/navigation', () => ({ invalidate: vi.fn() }));

afterEach(cleanup);

function campaign(overrides: Partial<Campaign>): Campaign {
	return {
		id: '00000000-0000-0000-0000-00000000000' + Math.floor(Math.random() * 9 + 1),
		name: 'Unnamed campaign',
		status: 'draft',
		promotionPosture: 'expertise_first',
		productContext: null,
		icp: null,
		keywords: [],
		subreddits: [],
		competitors: [],
		approvedClaims: [],
		prohibitedClaims: [],
		createdAt: '2026-08-22T10:00:00Z',
		archivedAt: null,
		...overrides
	};
}

describe('campaigns/+page.svelte', () => {
	it('lists campaigns with their status and lifecycle actions', () => {
		render(Page, {
			data: {
				apiReachable: true,
				detail: null,
				campaigns: [
					campaign({ id: 'a', name: 'Draft research objective', status: 'draft' }),
					campaign({ id: 'b', name: 'Running post', status: 'active' })
				]
			}
		});

		expect(screen.getByText('Draft research objective')).toBeInTheDocument();
		expect(screen.getByText('Running post')).toBeInTheDocument();
		expect(screen.getByText('draft')).toBeInTheDocument();
		expect(screen.getByText('active')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Activate' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
	});

	it('retires archived campaigns: badge shown, no lifecycle or edit affordances', () => {
		render(Page, {
			data: {
				apiReachable: true,
				detail: null,
				campaigns: [
					campaign({ id: 'a', name: 'Old post', status: 'archived', archivedAt: '2026-08-22T12:00:00Z' })
				]
			}
		});

		expect(screen.getByText('Old post')).toBeInTheDocument();
		expect(screen.getByText('archived')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Activate' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
	});

	it('offers a creation form with the required positioning fields', () => {
		render(Page, { data: { apiReachable: true, detail: null, campaigns: [] } });

		const createForm = document.querySelector('form[action="?/create"]') as HTMLElement;
		expect(createForm).not.toBeNull();
		// Scoped: per-campaign edit forms repeat the same field labels.
		expect(within(createForm).getByLabelText('Name')).toBeRequired();
		expect(within(createForm).getByLabelText('Promotion posture')).toBeInTheDocument();
		expect(within(createForm).getByLabelText('Keywords')).toBeInTheDocument();
		expect(within(createForm).getByLabelText('Approved claims')).toBeInTheDocument();
		expect(within(createForm).getByLabelText('Prohibited claims')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Create campaign' })).toBeInTheDocument();
	});

	it('summarizes the claim policy on campaigns that carry one', () => {
		render(Page, {
			data: {
				apiReachable: true,
				detail: null,
				campaigns: [
					campaign({
						id: 'a',
						name: 'Guarded post',
						approvedClaims: ['Aptori runs in CI'],
						prohibitedClaims: ['100% vulnerability coverage']
					})
				]
			}
		});

		expect(
			screen.getByText('Claim policy: 1 approved, 1 prohibited')
		).toBeInTheDocument();
	});

	it('surfaces action failures returned by the form actions', () => {
		render(Page, {
			data: { apiReachable: true, detail: null, campaigns: [] },
			form: { message: 'That lifecycle change is not allowed.' }
		});

		expect(screen.getByText('That lifecycle change is not allowed.')).toBeInTheDocument();
	});

	it('surfaces a reachable backend failure instead of an empty workspace', () => {
		render(Page, {
			data: {
				apiReachable: true,
				detail: 'Unexpected response (HTTP 500)',
				campaigns: []
			}
		});

		expect(screen.getByText('Unexpected response (HTTP 500)')).toBeInTheDocument();
		expect(screen.queryByText('No campaigns yet.')).not.toBeInTheDocument();
	});

	it('collects claims one per line', () => {
		render(Page, { data: { apiReachable: true, detail: null, campaigns: [] } });

		const createForm = document.querySelector('form[action="?/create"]') as HTMLElement;
		expect(within(createForm).getByLabelText('Approved claims').tagName).toBe('TEXTAREA');
		expect(within(createForm).getByLabelText('Prohibited claims').tagName).toBe('TEXTAREA');
	});

	it('explains when the backend is unreachable', () => {
		render(Page, {
			data: { apiReachable: false, detail: 'Backend did not answer', campaigns: [] }
		});

		expect(screen.getByText('Backend did not answer')).toBeInTheDocument();
	});
});
