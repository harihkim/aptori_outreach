import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({ invalidate: vi.fn().mockResolvedValue(undefined) }));

import { invalidate } from '$app/navigation';
import Page from './+page.svelte';
import {
	parseDiscoveryRunResponse,
	parseObservationsResponse,
	type DiscoveryRunBody
} from '$lib/discovery';

const plan = {
	source: 'prototype-smoke',
	provider_variant: 'obscura-duckduckgo-lite@2026-08-21',
	config_sha256: 'c'.repeat(64),
	document_sha256: 'd'.repeat(64),
	queries: [
		{
			id: 'q01-api-security-broad',
			pattern: 'broad_high_noise',
			query: 'API security',
			subreddits: []
		},
		{
			id: 'q02-appsec-tools-broad',
			pattern: null,
			query: 'application security tools',
			subreddits: ['netsec']
		}
	]
};

function runBody(overrides: Partial<DiscoveryRunBody> = {}): DiscoveryRunBody {
	return {
		id: '6a9a2f0e-2222-4bbb-8ccc-000000000002',
		campaign_id: '6a9a2f0e-1111-4bbb-8ccc-000000000001',
		workspace_id: '00000000-0000-0000-0000-000000000001',
		status: 'queued',
		method_plan: plan,
		correlation_id: 'corr1234567890ab',
		metrics: null,
		started_at: null,
		completed_at: null,
		created_at: '2026-08-23T10:00:00Z',
		updated_at: '2026-08-23T10:00:00Z',
		...overrides
	};
}

function observation(status: string, failureClass: string | null = null, queryId = 'q01-api-security-broad') {
	const unique = String(Math.abs(hash(status + (failureClass ?? '') + queryId + observationCounter))).padStart(12, '0');
	observationCounter += 1;
	return {
		id: `6a9a2f0e-3333-4bbb-8ccc-${unique}`,
		query_id: queryId,
		capability: 'discovery',
		status,
		failure_class: failureClass,
		failure_reason: failureClass ? 'the provider said no' : null,
		provider_variant: 'obscura-duckduckgo-lite@2026-08-21',
		config_sha256: 'c'.repeat(64),
		schema_version: 1,
		candidate_count: 3,
		candidates: [],
		normalized_sha256: null,
		elapsed_ms: 1250,
		evidence_directory: `/evidence-runs/run/attempt-${queryId}`,
		correlation_id: 'corr1234567890ab',
		started_at: '2026-08-23T10:00:00Z',
		completed_at: '2026-08-23T10:00:01Z',
		created_at: '2026-08-23T10:00:01Z'
	};
}

function hash(value: string): number {
	let h = 0;
	for (let i = 0; i < value.length; i += 1) {
		h = (h * 31 + value.charCodeAt(i)) | 0;
	}
	return h;
}

let observationCounter = 0;

function pageData(
	runBodyValue: DiscoveryRunBody,
	items: unknown[] = [],
	nextCursor: string | null = null
) {
	const runState = parseDiscoveryRunResponse({ httpStatus: 200, body: runBodyValue });
	const observationsState = parseObservationsResponse({
		httpStatus: 200,
		body: { items, next_cursor: nextCursor }
	});
	return {
		runState,
		observationsState,
		params: {
			campaignId: runBodyValue.campaign_id,
			runId: runBodyValue.id
		}
	};
}

/** A transient outage after a previously successful poll of a live run. */
function unreachablePageData(runBodyValue: DiscoveryRunBody) {
	const { run } = parseDiscoveryRunResponse({ httpStatus: 200, body: runBodyValue });
	return {
		runState: { apiReachable: false, run, detail: 'Backend did not answer' },
		observationsState: {
			apiReachable: false,
			items: [],
			nextCursor: null,
			detail: 'Backend did not answer'
		},
		params: {
			campaignId: runBodyValue.campaign_id,
			runId: runBodyValue.id
		}
	};
}

afterEach(() => {
	vi.useRealTimers();
	cleanup();
});

beforeEach(() => {
	vi.mocked(invalidate).mockClear();
});

describe('discovery run page', () => {
	it('shows the run header with status badge and honest cost reporting', () => {
		render(Page, {
			data: pageData(runBody({ status: 'running', started_at: '2026-08-23T10:00:00Z' }))
		});

		expect(screen.getByText('running')).toBeInTheDocument();
		expect(screen.getByText('Not priced')).toBeInTheDocument();
		expect(screen.getByText(/Currency cost:/)).toBeInTheDocument();
		expect(screen.getByText('obscura-duckduckgo-lite@2026-08-21')).toBeInTheDocument();
		expect(screen.getAllByText(/2 queries/).length).toBeGreaterThan(0);
	});

	it('shows measured retrieval usage next to latency without inventing zeros', () => {
		render(
			Page,
			{
				data: pageData(
					runBody({
						status: 'succeeded',
						metrics: {
							cost_status: 'unpriced',
							cost_usd: null,
							usage: { request_count: 37, bytes_transferred: 1257438 }
						}
					})
				)
			}
		);

		expect(screen.getByText(/Measured usage:/)).toBeInTheDocument();
		expect(
			screen.getByText('37 requests · 1.2 MB')
		).toBeInTheDocument();
	});

	it('renders no usage line for the retired top-level metric shape', () => {
		render(
			Page,
			{
				data: pageData(
					runBody({
						status: 'succeeded',
						metrics: {
							browser_wall_time_ms: 12340,
							bytes_transferred: 1257438,
							network_request_count: 37
						}
					})
				)
			}
		);

		expect(screen.queryByText(/Measured usage:/)).not.toBeInTheDocument();
	});

	it('leaves the usage line out entirely when nothing was measured', () => {
		render(Page, { data: pageData(runBody()) });

		expect(screen.queryByText(/Measured usage:/)).not.toBeInTheDocument();
	});

	it('lists the frozen queries in an expandable plan section', () => {
		render(Page, { data: pageData(runBody()) });

		const summary = screen.getByText('Frozen queries');
		expect(summary).toBeInTheDocument();
		expect(screen.getByText('API security')).toBeInTheDocument();
		expect(screen.getByText('application security tools')).toBeInTheDocument();
	});

	it('teaches the operator while waiting for the first observation', () => {
		render(Page, { data: pageData(runBody()) });

		expect(
			screen.getByText(
				'No observations recorded yet — this page polls while the run executes.'
			)
		).toBeInTheDocument();
	});

	it('renders observation rows with status, failures, and latency', () => {
		render(
			Page,
			{
				data: pageData(runBody({ status: 'partial' }), [
					observation('blocked', 'rate_limited_by_provider'),
					observation('success', null, 'q02-appsec-tools-broad')
				])
			}
		);

		const table = screen.getByRole('table');
		expect(within(table).getByText('q01-api-security-broad')).toBeInTheDocument();
		expect(within(table).getByText('q02-appsec-tools-broad')).toBeInTheDocument();
		expect(screen.getByText('rate_limited_by_provider')).toBeInTheDocument();
		expect(screen.getAllByText('the provider said no').length).toBeGreaterThan(0);
		expect(screen.getAllByText('1.3 s').length).toBeGreaterThan(0);
		expect(within(table).getByText('success')).toBeInTheDocument();
		expect(within(table).getByText('blocked')).toBeInTheDocument();
	});

	it('surfaces a failure banner counting observations by class', () => {
		render(
			Page,
			{
				data: pageData(runBody({ status: 'failed' }), [
					observation('blocked', 'rate_limited_by_provider'),
					observation('failed', 'transport_timeout'),
					observation('failed', 'transport_timeout')
				])
			}
		);

		const banner = screen.getByRole('alert');
		expect(banner).toHaveTextContent('2 × transport_timeout');
		expect(banner).toHaveTextContent('1 × rate_limited_by_provider');
	});

	it('polls with backoff while the run is live and the backend answers', async () => {
		vi.useFakeTimers();
		render(Page, { data: pageData(runBody({ status: 'queued' })) });

		await vi.advanceTimersByTimeAsync(3000);
		await vi.advanceTimersByTimeAsync(6000);

		expect(invalidate).toHaveBeenCalledTimes(2);
		expect(invalidate).toHaveBeenCalledWith('app:discovery-run');
	});

	it('keeps polling an unreachable backend with growing backoff while the run is live', async () => {
		vi.useFakeTimers();
		render(Page, { data: unreachablePageData(runBody({ status: 'running' })) });

		await vi.advanceTimersByTimeAsync(3000);
		expect(invalidate).toHaveBeenCalledTimes(1);

		// 3s -> 6s: nothing fires before the doubled delay elapses.
		await vi.advanceTimersByTimeAsync(5000);
		expect(invalidate).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1000);
		expect(invalidate).toHaveBeenCalledTimes(2);

		// 6s -> 12s -> capped at 15s.
		await vi.advanceTimersByTimeAsync(12_000);
		expect(invalidate).toHaveBeenCalledTimes(3);
		await vi.advanceTimersByTimeAsync(14_000);
		expect(invalidate).toHaveBeenCalledTimes(3);
		await vi.advanceTimersByTimeAsync(2_000);
		expect(invalidate).toHaveBeenCalledTimes(4);
		// The cap holds: 16 seconds yields exactly one further poll.
		await vi.advanceTimersByTimeAsync(16_000);
		expect(invalidate).toHaveBeenCalledTimes(5);
	});

	it('tells the operator the backend is unreachable instead of showing a dead end', async () => {
		vi.useFakeTimers();
		render(Page, { data: unreachablePageData(runBody({ status: 'running' })) });

		const notice = screen.getByTestId('unreachable-retrying');
		expect(notice).toHaveTextContent('Backend unreachable - retrying...');
	});

	it('stops polling once the run reaches a terminal status', async () => {
		vi.useFakeTimers();
		render(Page, { data: pageData(runBody({ status: 'succeeded' })) });

		await vi.advanceTimersByTimeAsync(9000);

		expect(invalidate).not.toHaveBeenCalled();
	});

	it('stops polling an unreachable backend once the last known status is terminal', async () => {
		vi.useFakeTimers();
		render(Page, { data: unreachablePageData(runBody({ status: 'failed' })) });

		await vi.advanceTimersByTimeAsync(60_000);

		expect(invalidate).not.toHaveBeenCalled();
	});

	it('says so when older observations are hidden behind a cursor', () => {
		vi.useFakeTimers();
		render(
			Page,
			{
				data: pageData(
					runBody({ status: 'partial' }),
					[observation('success')],
					'cursor-older-page'
				)
			}
		);

		expect(screen.getByTestId('older-observations')).toHaveTextContent(
			'+ older observations hidden'
		);
	});

	it('does not claim hidden observations when the page is complete', () => {
		vi.useFakeTimers();
		render(Page, { data: pageData(runBody({ status: 'partial' }), [observation('success')]) });

		expect(screen.queryByTestId('older-observations')).not.toBeInTheDocument();
	});
});
