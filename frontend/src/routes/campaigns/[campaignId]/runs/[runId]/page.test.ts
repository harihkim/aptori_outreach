import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen, within } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({ invalidate: vi.fn().mockResolvedValue(undefined) }));

import { invalidate } from '$app/navigation';
import Page from './+page.svelte';
import {
	parseDiscoveryRunResponse,
	parseConversationsResponse,
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
		evidence: { state: 'legacy' },
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

class FakeEventSource {
	static instances: FakeEventSource[] = [];
	readonly url: string;
	onopen: (() => void) | null = null;
	onerror: (() => void) | null = null;
	private listeners = new Map<string, (event: Event) => void>();
	closed = false;

	constructor(url: string) {
		this.url = url;
		FakeEventSource.instances.push(this);
	}

	addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
		this.listeners.set(type, listener as (event: Event) => void);
	}

	close(): void {
		this.closed = true;
	}

	open(): void {
		this.onopen?.();
	}

	fail(): void {
		this.onerror?.();
	}

	emit(type: string, data: string): void {
		this.listeners.get(type)?.({ type, data } as MessageEvent<string>);
	}
}

function pageData(
	runBodyValue: DiscoveryRunBody,
	items: unknown[] = [],
	nextCursor: string | null = null,
	conversationsBody: unknown = {
		items: [],
		expected_count: 0,
		fetched_count: 0,
		normalized_count: 0,
		processing_complete: true
	}
) {
	const runState = parseDiscoveryRunResponse({ httpStatus: 200, body: runBodyValue });
	const observationsState = parseObservationsResponse({
		httpStatus: 200,
		body: { items, next_cursor: nextCursor }
	});
	const conversationsState = parseConversationsResponse({
		httpStatus: 200,
		body: conversationsBody
	});
	return {
		runState,
		observationsState,
		conversationsState,
		params: {
			campaignId: runBodyValue.campaign_id,
			runId: runBodyValue.id
		}
	};
}

/** A transient outage after a previously successful poll of a live run. */
function unreachablePageData(runBodyValue: DiscoveryRunBody) {
	const { run } = parseDiscoveryRunResponse({ httpStatus: 200, body: runBodyValue });
	const terminal = ['succeeded', 'partial', 'failed', 'cancelled'].includes(runBodyValue.status);
	return {
		runState: { apiReachable: false, run, detail: 'Backend did not answer' },
		observationsState: {
			apiReachable: false,
			items: [],
			nextCursor: null,
			detail: 'Backend did not answer'
		},
		conversationsState: {
			apiReachable: false,
			items: [],
			expectedCount: 0,
			fetchedCount: 0,
			normalizedCount: 0,
			processingComplete: terminal,
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
	vi.unstubAllGlobals();
	cleanup();
});

beforeEach(() => {
	vi.mocked(invalidate).mockClear();
});

describe('discovery run page', () => {
	it('connects live progress through the same-origin SSE stream', () => {
		vi.stubGlobal('EventSource', FakeEventSource);
		FakeEventSource.instances = [];
		render(Page, { data: pageData(runBody({ status: 'running' })) });
		const source = FakeEventSource.instances[0];
		expect(source.url).toBe(
			'/api/discovery-runs/6a9a2f0e-2222-4bbb-8ccc-000000000002/events'
		);

		source.open();
		flushSync();
		expect(screen.getByTestId('progress-transport')).toHaveTextContent(
			'Live progress connected'
		);
		source.emit(
			'discovery.started',
			JSON.stringify({
				id: 'event-1',
				type: 'discovery.started',
				run_id: '6a9a2f0e-2222-4bbb-8ccc-000000000002',
				workspace_id: '00000000-0000-0000-0000-000000000001',
				correlation_id: 'corr1234567890ab',
				occurred_at: '2026-08-30T10:00:00Z',
				payload: { status: 'running' }
			})
		);
		expect(invalidate).toHaveBeenCalledWith('app:discovery-run');
	});

	it('keeps a terminal discovery stream open until conversation processing completes', () => {
		vi.stubGlobal('EventSource', FakeEventSource);
		FakeEventSource.instances = [];
		render(Page, {
			data: pageData(runBody({ status: 'succeeded' }), [], null, {
				items: [],
				expected_count: 1,
				fetched_count: 0,
				normalized_count: 0,
				processing_complete: false
			})
		});
		const source = FakeEventSource.instances[0];

		source.emit(
			'discovery.completed',
			JSON.stringify({
				id: 'event-complete-discovery',
				type: 'discovery.completed',
				run_id: '6a9a2f0e-2222-4bbb-8ccc-000000000002',
				workspace_id: '00000000-0000-0000-0000-000000000001',
				correlation_id: 'corr1234567890ab',
				occurred_at: '2026-09-01T12:00:00Z',
				payload: { status: 'succeeded' }
			})
		);
		expect(source.closed).toBe(false);

		source.emit(
			'conversation.processing_completed',
			JSON.stringify({
				id: 'event-complete-conversations',
				type: 'conversation.processing_completed',
				run_id: '6a9a2f0e-2222-4bbb-8ccc-000000000002',
				workspace_id: '00000000-0000-0000-0000-000000000001',
				correlation_id: 'corr1234567890ab',
				occurred_at: '2026-09-01T12:00:01Z',
				payload: { expected_count: 1, fetched_count: 1, normalized_count: 1 }
			})
		);
		expect(source.closed).toBe(true);
	});

	it('closes a failed stream and leaves the polling fallback active', async () => {
		vi.useFakeTimers();
		vi.stubGlobal('EventSource', FakeEventSource);
		FakeEventSource.instances = [];
		render(Page, { data: pageData(runBody({ status: 'running' })) });
		const source = FakeEventSource.instances[0];

		source.fail();
		flushSync();
		expect(source.closed).toBe(true);
		expect(screen.getByTestId('progress-transport')).toHaveTextContent(
			'polling fallback active'
		);
		await vi.advanceTimersByTimeAsync(3000);
		expect(invalidate).toHaveBeenCalledWith('app:discovery-run');
	});

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

	it('shows each durable Candidate to Conversation transition', () => {
		render(Page, {
			data: pageData(runBody({ status: 'succeeded' }), [], null, {
				items: [
					{
						external_source_id: 't3_waiting',
						url: 'https://www.reddit.com/r/example/comments/waiting/topic/',
						title: 'Waiting for retrieval',
						rank: 1,
						state: 'candidate',
						retrieval_status: null,
						conversation: null
					},
					{
						external_source_id: 't3_ready',
						url: 'https://www.reddit.com/r/example/comments/ready/topic/',
						title: 'Normalized discussion',
						rank: 2,
						state: 'conversation',
						retrieval_status: 'success',
						conversation: {
							id: 'conversation-ready',
							source_platform: 'reddit',
							canonical_external_discussion_id: 't3_ready',
							current_version: {
								id: 'version-ready',
								normalizer_version: 'reddit-thread/v1',
								normalized_sha256: 'a'.repeat(64),
								normalized_content_sha256: 'b'.repeat(64),
								source_tree_exhausted: true,
								created_at: '2026-09-01T12:00:00Z'
							}
						}
					}
				],
				expected_count: 2,
				fetched_count: 1,
				normalized_count: 1,
				processing_complete: false
			})
		});

		const list = screen.getByTestId('candidate-conversation-list');
		expect(within(list).getByText('Waiting for retrieval')).toBeInTheDocument();
		expect(within(list).getByText('Normalized discussion')).toBeInTheDocument();
		expect(within(list).getByText('Candidate')).toBeInTheDocument();
		expect(within(list).getByText('Conversation')).toBeInTheDocument();
		expect(within(list).getByText(/reddit-thread\/v1/)).toBeInTheDocument();
		expect(within(list).getByText(/complete tree/)).toBeInTheDocument();
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
					observation('blocked', 'wrapper_error'),
					observation('success', null, 'q02-appsec-tools-broad')
				])
			}
		);

		const table = screen.getByRole('table');
		expect(within(table).getByText('q01-api-security-broad')).toBeInTheDocument();
		expect(within(table).getByText('q02-appsec-tools-broad')).toBeInTheDocument();
		expect(screen.getByText('wrapper_error')).toBeInTheDocument();
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
					observation('blocked', 'wrapper_error'),
					observation('failed', 'transport_timeout'),
					observation('failed', 'transport_timeout')
				])
			}
		);

		const banner = screen.getByRole('alert');
		expect(banner).toHaveTextContent('2 × transport_timeout');
		expect(banner).toHaveTextContent('1 × wrapper_error');
	});

	it('polls with backoff while the run is live and the backend answers', async () => {
		vi.useFakeTimers();
		render(Page, { data: pageData(runBody({ status: 'queued' })) });

		await vi.advanceTimersByTimeAsync(3000);
		await vi.advanceTimersByTimeAsync(6000);

		expect(invalidate).toHaveBeenCalledTimes(2);
		expect(invalidate).toHaveBeenCalledWith('app:discovery-run');
	});

	it('follows the exact backoff ladder 3s, 6s, 12s, then caps at 15s', async () => {
		vi.useFakeTimers();
		render(Page, { data: pageData(runBody({ status: 'running' })) });

		await vi.advanceTimersByTimeAsync(2999);
		expect(invalidate).toHaveBeenCalledTimes(0);
		await vi.advanceTimersByTimeAsync(1);
		expect(invalidate).toHaveBeenCalledTimes(1);

		await vi.advanceTimersByTimeAsync(5999);
		expect(invalidate).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1);
		expect(invalidate).toHaveBeenCalledTimes(2);

		await vi.advanceTimersByTimeAsync(11_999);
		expect(invalidate).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(1);
		expect(invalidate).toHaveBeenCalledTimes(3);

		await vi.advanceTimersByTimeAsync(14_999);
		expect(invalidate).toHaveBeenCalledTimes(3);
		await vi.advanceTimersByTimeAsync(1);
		expect(invalidate).toHaveBeenCalledTimes(4);

		// The cap holds thereafter: each further window yields one poll.
		for (let expected = 4; expected <= 6; expected += 1) {
			await vi.advanceTimersByTimeAsync(14_999);
			expect(invalidate).toHaveBeenCalledTimes(expected);
			await vi.advanceTimersByTimeAsync(1);
			expect(invalidate).toHaveBeenCalledTimes(expected + 1);
		}
	});

	it('restarts the backoff at 3s once a poll succeeds again after failures', async () => {
		vi.useFakeTimers();
		const { rerender } = render(Page, { data: unreachablePageData(runBody({ status: 'running' })) });

		await vi.advanceTimersByTimeAsync(3000);
		expect(invalidate).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(6000);
		expect(invalidate).toHaveBeenCalledTimes(2);

		// The backend answers again: flip to a reachable payload mid-backoff.
		rerender({ data: pageData(runBody({ status: 'running' })) });
		flushSync();

		// The next poll comes exactly 3s after the success, not on the old
		// doubled delay (which was still ~12s out).
		await vi.advanceTimersByTimeAsync(2999);
		expect(invalidate).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(1);
		expect(invalidate).toHaveBeenCalledTimes(3);

		// Afterwards the ladder resumes from the fresh counter: 6s next.
		await vi.advanceTimersByTimeAsync(5999);
		expect(invalidate).toHaveBeenCalledTimes(3);
		await vi.advanceTimersByTimeAsync(1);
		expect(invalidate).toHaveBeenCalledTimes(4);
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

	it('cancels the pending poll when a live run flips to a terminal status', async () => {
		vi.useFakeTimers();
		const { rerender } = render(Page, { data: pageData(runBody({ status: 'queued' })) });

		await vi.advanceTimersByTimeAsync(3000);
		expect(invalidate).toHaveBeenCalledTimes(1);

		rerender({ data: pageData(runBody({ status: 'succeeded' })) });
		flushSync();

		// The 6s follow-up timer was torn down with the live chain.
		await vi.advanceTimersByTimeAsync(60_000);
		expect(invalidate).toHaveBeenCalledTimes(1);
	});

	it('clears the pending timer on unmount so no further polls fire', async () => {
		vi.useFakeTimers();
		const { unmount } = render(Page, { data: pageData(runBody({ status: 'running' })) });

		await vi.advanceTimersByTimeAsync(3000);
		expect(invalidate).toHaveBeenCalledTimes(1);

		unmount();
		await vi.advanceTimersByTimeAsync(30_000);

		expect(invalidate).toHaveBeenCalledTimes(1);
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
