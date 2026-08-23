import '@testing-library/jest-dom/vitest';

import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Page from './+page.svelte';
import { invalidate } from '$app/navigation';
import {
	CREATE_SUBMISSION_ID,
	nextActions,
	transitionSubmissionId,
	updateSubmissionId,
	type Campaign
} from '$lib/campaigns';
import { discoverySubmissionId } from '$lib/discovery';

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
		updatedAt: '2026-08-23T11:00:00Z',
		archivedAt: null,
		...overrides
	};
}

function pageData(
	campaigns: Campaign[] = [],
	detail: string | null = null,
	apiReachable = true,
	nextCursor: string | null = null,
	currentCursor: string | null = null
) {
	const submissionKeys: Record<string, string> = {
		[CREATE_SUBMISSION_ID]: 'key:create'
	};
	for (const item of campaigns) {
		if (item.status !== 'archived') {
			submissionKeys[updateSubmissionId(item.id)] = `key:update:${item.id}`;
		}
		for (const action of nextActions(item.status)) {
			submissionKeys[transitionSubmissionId(item.id, action.status)] =
				`key:transition:${item.id}:${action.status}`;
		}
		if (item.status === 'active') {
			submissionKeys[discoverySubmissionId(item.id)] = `key:discovery:${item.id}`;
		}
	}
	return { apiReachable, detail, campaigns, nextCursor, currentCursor, submissionKeys };
}

describe('campaigns/+page.svelte', () => {
	it('lists campaigns with their status and lifecycle actions', () => {
		render(Page, {
			data: pageData([
				campaign({ id: 'a', name: 'Draft research objective', status: 'draft' }),
				campaign({ id: 'b', name: 'Running post', status: 'active' })
			])
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
			data: pageData([
				campaign({
					id: 'a',
					name: 'Old post',
					status: 'archived',
					archivedAt: '2026-08-22T12:00:00Z'
				})
			])
		});

		expect(screen.getByText('Old post')).toBeInTheDocument();
		expect(screen.getByText('archived')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Activate' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
	});

	it('offers a creation form with the required positioning fields', () => {
		render(Page, { data: pageData() });

		const createForm = document.querySelector('form[action="?/create"]') as HTMLElement;
		expect(createForm).not.toBeNull();
		// Scoped: per-campaign edit forms repeat the same field labels.
		expect(within(createForm).getByLabelText('Name')).toBeRequired();
		expect(within(createForm).getByLabelText('Promotion posture')).toBeInTheDocument();
		expect(within(createForm).getByLabelText('Promotion posture')).toHaveValue(
			'expertise_first'
		);
		expect(within(createForm).getByLabelText('Keywords')).toBeInTheDocument();
		expect(within(createForm).getByLabelText('Approved claims')).toBeInTheDocument();
		expect(within(createForm).getByLabelText('Prohibited claims')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Create campaign' })).toBeInTheDocument();
	});

	it('shows when each campaign last changed', () => {
		render(Page, { data: pageData([campaign({ id: 'a', name: 'Changed campaign' })]) });

		expect(screen.getByText(/updated 2026-08-23/)).toBeInTheDocument();
	});

	it('summarizes the claim policy on campaigns that carry one', () => {
		render(Page, {
			data: pageData([
				campaign({
					id: 'a',
					name: 'Guarded post',
					approvedClaims: ['Aptori runs in CI'],
					prohibitedClaims: ['100% vulnerability coverage']
				})
			])
		});

		expect(
			screen.getByText('Claim policy: 1 approved, 1 prohibited')
		).toBeInTheDocument();
	});

	it('surfaces action failures returned by the form actions', () => {
		render(Page, {
			data: pageData(),
			form: {
				message: 'That lifecycle change is not allowed.',
				submission_id: CREATE_SUBMISSION_ID,
				idempotency_key: 'transition-key'
			}
		});

		expect(screen.getByText('That lifecycle change is not allowed.')).toBeInTheDocument();
	});

	it('surfaces a reachable backend failure instead of an empty workspace', () => {
		render(Page, {
			data: pageData([], 'Unexpected response (HTTP 500)')
		});

		expect(screen.getByText('Unexpected response (HTTP 500)')).toBeInTheDocument();
		expect(screen.queryByText('No campaigns yet.')).not.toBeInTheDocument();
	});

	it('edits every list one value per line', () => {
		render(Page, { data: pageData() });

		const createForm = document.querySelector('form[action="?/create"]') as HTMLElement;
		for (const label of ['Keywords', 'Subreddits', 'Competitors', 'Approved claims', 'Prohibited claims']) {
			expect(within(createForm).getByLabelText(label).tagName).toBe('TEXTAREA');
		}
	});

	it('keeps a stable submission key across a failed submission', () => {
		render(Page, {
			data: pageData(),
			form: {
				message: 'Backend did not answer.',
				submission_id: CREATE_SUBMISSION_ID,
				idempotency_key: 'stable-key'
			}
		});

		const createForm = document.querySelector('form[action="?/create"]') as HTMLElement;
		const hidden = createForm.querySelector(
			'input[name="idempotency_key"]'
		) as HTMLInputElement;
		expect(hidden.value).toBe('stable-key');
	});

	it('lets an operator intentionally start a new logical attempt', async () => {
		render(Page, {
			data: pageData(),
			form: {
				message: 'That lifecycle change is not allowed.',
				submission_id: CREATE_SUBMISSION_ID,
				idempotency_key: 'recorded-error-key'
			}
		});

		const createForm = document.querySelector('form[action="?/create"]') as HTMLElement;
		const hidden = createForm.querySelector(
			'input[name="idempotency_key"]'
		) as HTMLInputElement;
		expect(hidden.value).toBe('recorded-error-key');

		await fireEvent.click(screen.getByRole('button', { name: 'Start new attempt' }));

		expect(hidden.value).not.toBe('recorded-error-key');
		expect(hidden.value).toMatch(/^[0-9a-f-]{36}$/);
	});

	it('refreshes the campaign dependency without a full page reload', async () => {
		vi.mocked(invalidate).mockResolvedValue(undefined);
		render(Page, { data: pageData() });

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

		expect(invalidate).toHaveBeenCalledWith('app:campaigns');
	});

	it('offers bounded navigation across campaign pages', () => {
		render(Page, { data: pageData([], null, true, 'next-cursor', 'current-cursor') });

		expect(screen.getByRole('link', { name: 'Newest campaigns' })).toHaveAttribute(
			'href',
			'/campaigns'
		);
		expect(screen.getByRole('link', { name: 'Older campaigns' })).toHaveAttribute(
			'href',
			'/campaigns?cursor=next-cursor'
		);
	});

	it('gives every logical form its own submission key', () => {
		const active = campaign({ id: 'active-campaign', status: 'active' });
		render(Page, { data: pageData([active]) });

		const forms = Array.from(document.querySelectorAll('form'));
		const keys = forms.map((element) => {
			const input = element.querySelector(
				'input[name="idempotency_key"]'
			) as HTMLInputElement | null;
			return input?.value;
		});

		expect(keys).toHaveLength(5);
		expect(new Set(keys).size).toBe(5);
	});

	it('restores a failed key only to the form that submitted it', () => {
		const active = campaign({ id: 'active-campaign', status: 'active' });
		const failedId = transitionSubmissionId(active.id, 'paused');
		render(Page, {
			data: pageData([active]),
			form: {
				message: 'Backend did not answer.',
				submission_id: failedId,
				idempotency_key: 'failed-pause-key'
			}
		});

		const failedIdInput = document.querySelector(
			`input[name="submission_id"][value="${failedId}"]`
		) as HTMLInputElement;
		const failedForm = failedIdInput.closest('form') as HTMLFormElement;
		const failedKey = failedForm.querySelector(
			'input[name="idempotency_key"]'
		) as HTMLInputElement;
		const createKey = document.querySelector(
			'form[action="?/create"] input[name="idempotency_key"]'
		) as HTMLInputElement;

		expect(failedKey.value).toBe('failed-pause-key');
		expect(createKey.value).toBe('key:create');
	});

	it('explains when the backend is unreachable', () => {
		render(Page, {
			data: pageData([], 'Backend did not answer', false)
		});

		expect(screen.getByText('Backend did not answer')).toBeInTheDocument();
	});

	it('offers Run discovery only on active campaigns', () => {
		const active = campaign({ id: 'active-campaign', name: 'Live campaign', status: 'active' });
		const draft = campaign({ id: 'draft-campaign', name: 'Draft campaign', status: 'draft' });
		render(Page, { data: pageData([active, draft]) });

		expect(screen.getByRole('button', { name: 'Run discovery' })).toBeInTheDocument();

		const startForm = document.querySelector(
			'form[action="?/start-discovery"]'
		) as HTMLFormElement;
		expect(startForm).not.toBeNull();
		expect(
			(startForm.querySelector('input[name="campaign_id"]') as HTMLInputElement).value
		).toBe('active-campaign');
		expect(
			(startForm.querySelector('input[name="idempotency_key"]') as HTMLInputElement).value
		).toBe('key:discovery:active-campaign');
	});

	it('keeps discovery out of reach for draft and archived campaigns', () => {
		render(Page, {
			data: pageData([
				campaign({ id: 'a', name: 'Still drafting', status: 'draft' }),
				campaign({ id: 'b', name: 'Long gone', status: 'archived' })
			])
		});

		expect(screen.queryByRole('button', { name: 'Run discovery' })).not.toBeInTheDocument();
	});
});
