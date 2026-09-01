import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({ invalidate: vi.fn().mockResolvedValue(undefined) }));

import Page from './+page.svelte';
import { parseOpportunitiesResponse } from '$lib/opportunities';
import { opportunityBody } from '$lib/opportunities.test';

afterEach(cleanup);

function pageData(
	bodies: Record<string, unknown>[],
	{
		detail = null,
		status = 'open',
		campaignId = null
	}: { detail?: string | null; status?: string; campaignId?: string | null } = {}
) {
	const opportunitiesState =
		detail === null
			? parseOpportunitiesResponse({ httpStatus: 200, body: { items: bodies } })
			: { apiReachable: detail !== 'Backend did not answer', items: [], detail };
	return {
		opportunitiesState,
		campaignNames: { '6a9a2f0e-1111-4bbb-8ccc-000000000001': 'API security' },
		filters: { status, campaignId }
	};
}

describe('opportunity inbox', () => {
	it('renders the ranked list with score, factors, rationale, age, action, and provenance', () => {
		const second = opportunityBody({
			id: '7a9a2f0e-4444-4bbb-8ccc-000000000009',
			opportunity_score: 0.21,
			post_created_at: '2026-08-20T10:00:00Z'
		});
		second.analysis = {
			...(second.analysis as Record<string, unknown>),
			recommended_action: 'monitor',
			rationale: 'Old thread with mild pain.'
		};
		render(Page, { data: pageData([opportunityBody(), second]) });

		const list = screen.getByTestId('opportunity-list');
		const rows = within(list).getAllByRole('listitem');
		expect(rows).toHaveLength(2);

		const top = within(rows[0]);
		expect(top.getByText('#1')).toBeInTheDocument();
		expect(top.getByTestId('opportunity-score')).toHaveTextContent('0.87');
		expect(top.getByRole('link', { name: 'Token rotation keeps failing' })).toHaveAttribute(
			'href',
			'https://www.reddit.com/r/netsec/comments/x/rotation/'
		);
		expect(top.getByText('API security')).toBeInTheDocument();
		expect(top.getByText('r/netsec')).toBeInTheDocument();
		expect(top.getByText('Reply helpfully')).toBeInTheDocument();
		expect(top.getByText('Open')).toBeInTheDocument();
		expect(top.getByText('Direct problem fit, but the author did not ask for vendors.')).toBeInTheDocument();

		const breakdown = within(top.getByTestId('factor-breakdown'));
		expect(breakdown.getByText('Relevance')).toBeInTheDocument();
		expect(breakdown.getByText('0.94')).toBeInTheDocument();
		expect(breakdown.getByText('Promotion fit (unscored)')).toBeInTheDocument();
		expect(breakdown.getByText('0.34')).toBeInTheDocument();

		expect(top.getByTestId('provenance')).toHaveTextContent(
			'analyze_conversation@1 · prompt 2026-09-02.1 · schema 1 · configured-model-2026 via llm.example.test (ordinary tier) · 908 tokens'
		);

		const runnerUp = within(rows[1]);
		expect(runnerUp.getByText('#2')).toBeInTheDocument();
		expect(runnerUp.getByTestId('opportunity-score')).toHaveTextContent('0.21');
		expect(runnerUp.getByText('Monitor')).toBeInTheDocument();
		expect(runnerUp.getByText(/\d+d old/)).toBeInTheDocument();
	});

	it('explains an empty inbox in terms of the pipeline', () => {
		render(Page, { data: pageData([], { status: 'saved' }) });
		expect(screen.getByText(/No saved opportunities yet/)).toBeInTheDocument();
		expect(screen.queryByTestId('opportunity-list')).not.toBeInTheDocument();
	});

	it('surfaces backend failures instead of an empty ranking', () => {
		render(Page, { data: pageData([], { detail: 'Backend did not answer' }) });
		expect(screen.getByRole('alert')).toHaveTextContent('Backend did not answer');
	});

	it('keeps the filters in the form so the view is shareable', () => {
		render(Page, {
			data: pageData([], { status: 'dismissed', campaignId: '6a9a2f0e-1111-4bbb-8ccc-000000000001' })
		});
		const filters = within(screen.getByTestId('inbox-filters'));
		expect(filters.getByLabelText('Status')).toHaveValue('dismissed');
		expect(filters.getByLabelText('Campaign')).toHaveValue('6a9a2f0e-1111-4bbb-8ccc-000000000001');
		expect(filters.getByRole('option', { name: 'API security' })).toBeInTheDocument();
	});
});
