import { describe, expect, it } from 'vitest';

import statusesContractJson from '../../../contracts/discovery-run-statuses.json';

import {
	OBSERVATION_STATUSES,
	RUN_STATUSES,
	USABLE_STATUSES,
	costLabel,
	costStatusOf,
	explainDiscoveryError,
	latencyLabel,
	observationTone,
	parseDiscoveryRunResponse,
	parseObservationsResponse,
	runStatusTone,
	usageLabel
} from '$lib/discovery';

type StatusesContract = {
	schemaVersion: number;
	runStatuses: string[];
	observationStatuses: string[];
	usableStatuses: string[];
};

const contract = statusesContractJson as StatusesContract;

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

const runBody = {
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
	updated_at: '2026-08-23T10:00:00Z'
};

const observationBody = {
	id: '6a9a2f0e-3333-4bbb-8ccc-000000000003',
	query_id: 'q01-api-security-broad',
	capability: 'discovery',
	status: 'success',
	failure_class: null,
	failure_reason: null,
	provider_variant: 'obscura-duckduckgo-lite@2026-08-21',
	config_sha256: 'c'.repeat(64),
	schema_version: 1,
	candidate_count: 3,
	candidates: [{ title: 't' }],
	normalized_sha256: 'a'.repeat(64),
	elapsed_ms: 1250,
	evidence_directory: '/evidence-runs/run/attempt-1',
	correlation_id: 'corr1234567890ab',
	started_at: '2026-08-23T10:00:00Z',
	completed_at: '2026-08-23T10:00:01Z',
	created_at: '2026-08-23T10:00:01Z'
};

describe('discovery status vocabulary', () => {
	it('matches the frozen backend contract', () => {
		expect(contract.schemaVersion).toBe(1);
		expect([...RUN_STATUSES]).toEqual(contract.runStatuses);
		expect([...OBSERVATION_STATUSES]).toEqual(contract.observationStatuses);
		expect([...USABLE_STATUSES]).toEqual(contract.usableStatuses);
	});
});

describe('parseDiscoveryRunResponse', () => {
	it('reports an unreachable backend without inventing state', () => {
		const state = parseDiscoveryRunResponse({ httpStatus: null, body: null });
		expect(state.apiReachable).toBe(false);
		expect(state.run).toBeNull();
		expect(state.detail).toBe('Backend did not answer');
	});

	it('maps a valid queued run into camelCase view state', () => {
		const state = parseDiscoveryRunResponse({ httpStatus: 200, body: runBody });

		expect(state.apiReachable).toBe(true);
		expect(state.detail).toBeNull();
		const run = state.run;
		if (!run) {
			throw new Error('run should have parsed');
		}
		expect(run.id).toBe(runBody.id);
		expect(run.campaignId).toBe(runBody.campaign_id);
		expect(run.status).toBe('queued');
		expect(run.correlationId).toBe('corr1234567890ab');
		expect(run.metrics).toBeNull();
		expect(run.startedAt).toBeNull();
		expect(run.methodPlan.source).toBe('prototype-smoke');
		expect(run.methodPlan.providerVariant).toBe('obscura-duckduckgo-lite@2026-08-21');
		expect(run.methodPlan.documentSha256).toBe('d'.repeat(64));
		expect(run.methodPlan.queries).toHaveLength(2);
		expect(run.methodPlan.queries[0]).toEqual({
			id: 'q01-api-security-broad',
			pattern: 'broad_high_noise',
			query: 'API security',
			subreddits: []
		});
	});

	it('maps every legal run status and rejects unknown ones', () => {
		for (const status of RUN_STATUSES) {
			const state = parseDiscoveryRunResponse({
				httpStatus: 200,
				body: { ...runBody, status }
			});
			expect(state.run?.status).toBe(status);
			expect(state.detail).toBeNull();
		}
		const unknown = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: { ...runBody, status: 'kind_of_running' }
		});
		expect(unknown.run).toBeNull();
		expect(unknown.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('passes run metrics through verbatim for formatters to read', () => {
		const metrics = {
			cost_status: 'unpriced',
			cost_usd: null,
			usage: { request_count: 37, bytes_transferred: 1257438 }
		};
		const state = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: { ...runBody, metrics }
		});
		expect(state.run?.metrics).toEqual(metrics);
	});

	it('surfaces domain errors as operator guidance', () => {
		const state = parseDiscoveryRunResponse({
			httpStatus: 409,
			body: { detail: { code: 'campaign_not_active', message: 'Campaign is draft.' } }
		});
		expect(state.apiReachable).toBe(true);
		expect(state.run).toBeNull();
		expect(state.detail).toBe('Only ACTIVE campaigns can run discovery.');
	});

	it('rejects malformed method plans and truncated bodies', () => {
		const brokenPlan = {
			...runBody,
			method_plan: { ...plan, queries: [{ id: 'q01', query: 42, subreddits: [] }] }
		};
		expect(
			parseDiscoveryRunResponse({ httpStatus: 200, body: brokenPlan }).run
		).toBeNull();
		expect(
			parseDiscoveryRunResponse({ httpStatus: 200, body: brokenPlan }).detail
		).toBe('Unexpected response (HTTP 200)');
		const truncated = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: { id: runBody.id, status: 'queued' }
		});
		expect(truncated.run).toBeNull();
	});
});

describe('parseObservationsResponse', () => {
	it('maps an empty page', () => {
		const state = parseObservationsResponse({
			httpStatus: 200,
			body: { items: [], next_cursor: null }
		});
		expect(state.apiReachable).toBe(true);
		expect(state.items).toEqual([]);
		expect(state.nextCursor).toBeNull();
		expect(state.detail).toBeNull();
	});

	it('camelCases every observation and keeps the cursor', () => {
		const state = parseObservationsResponse({
			httpStatus: 200,
			body: {
				items: [
					observationBody,
					{ ...observationBody, id: 'x2', status: 'runtime_verification_failed' }
				],
				next_cursor: 'next-page'
			}
		});

		expect(state.nextCursor).toBe('next-page');
		expect(state.items).toHaveLength(2);
		const first = state.items[0];
		expect(first.queryId).toBe('q01-api-security-broad');
		expect(first.status).toBe('success');
		expect(first.candidateCount).toBe(3);
		expect(first.candidates).toEqual([{ title: 't' }]);
		expect(first.elapsedMs).toBe(1250);
		expect(first.failureClass).toBeNull();
		expect(first.evidenceDirectory).toBe('/evidence-runs/run/attempt-1');
		expect(state.items[1].status).toBe('runtime_verification_failed');
	});

	it('rejects an item with an unknown observation status', () => {
		const state = parseObservationsResponse({
			httpStatus: 200,
			body: {
				items: [{ ...observationBody, status: 'fine_i_guess' }],
				next_cursor: null
			}
		});
		expect(state.items).toEqual([]);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('explains failures on non-200 pages', () => {
		const state = parseObservationsResponse({
			httpStatus: 404,
			body: { detail: { code: 'discovery_run_not_found', message: 'nope' } }
		});
		expect(state.apiReachable).toBe(true);
		expect(state.detail).toBe('Discovery run not found.');
	});
});

describe('explainDiscoveryError', () => {
	const cases: Array<[string, string]> = [
		['campaign_not_active', 'Only ACTIVE campaigns can run discovery.'],
		['campaign_not_found', 'Campaign not found.'],
		['discovery_run_not_found', 'Discovery run not found.'],
		[
			'worker_queue_unavailable',
			'The worker queue is unavailable; retrying the same request will safely re-enqueue.'
		],
		['retrieval_inputs_unavailable', 'Retrieval inputs are misconfigured on the backend.'],
		['unauthorized', 'The backend rejected the request token.'],
		['api_token_unconfigured', 'The backend has no API token configured.'],
		['workspace_unconfigured', 'The backend database needs its migrations run.'],
		['workspace_forbidden', 'The backend token cannot access this workspace.'],
		['page_cursor_invalid', 'That page link is invalid; return to the newest data.'],
		['idempotency_key_required', 'The form lost its submission key; refresh and try again.'],
		['idempotency_key_too_long', 'The form submission key is invalid; refresh and try again.'],
		[
			'idempotency_key_conflict',
			'This submission key was already used for different content.'
		],
		[
			'idempotency_key_reconciliation_required',
			'This older submission needs operator reconciliation before retrying.'
		]
	];
	for (const [code, expected] of cases) {
		it(`maps ${code}`, () => {
			expect(
				explainDiscoveryError(400, { detail: { code, message: 'backend words' } })
			).toBe(expected);
		});
	}

	it('explains validation failures and unknown failures', () => {
		expect(explainDiscoveryError(422, null)).toBe('Some fields were invalid.');
		expect(explainDiscoveryError(500, { surprise: true })).toBe(
			'Unexpected error (HTTP 500).'
		);
	});
});

describe('costLabel', () => {
	it('formats a reported numeric cost as USD', () => {
		expect(
			costLabel({ ...runBodyView(), metrics: { cost_status: 'reported', cost_usd: 1.5 } })
		).toBe('$1.50');
	});

	it('reads legacy payloads without cost_status as not priced, never money', () => {
		expect(costLabel({ ...runBodyView(), metrics: { cost_usd: 0.75 } })).toBe(
			'Not priced'
		);
	});

	it('says honestly when currency cost was never priced', () => {
		expect(costLabel({ ...runBodyView(), metrics: null })).toBe('Not priced');
		expect(
			costLabel({ ...runBodyView(), metrics: { cost_usd: 'unknown' } })
		).toBe('Not priced');
	});

	it('never renders a dollar figure for an unknown status word', () => {
		expect(
			costLabel({
				...runBodyView(),
				metrics: { cost_status: 'mystery', cost_usd: 4.2 }
			})
		).toBe('Not priced');
		expect(costStatusOf({ ...runBodyView(), metrics: { cost_status: 'mystery' } })).toBe(
			'unpriced'
		);
	});

	it('treats unknown status with a null cost as not priced', () => {
		expect(
			costLabel({
				...runBodyView(),
				metrics: { cost_status: 'mystery', cost_usd: null }
			})
		).toBe('Not priced');
	});
});

describe('cost pricing states (P1-COST decision B)', () => {
	it('never reads an unpriced run as free, even at zero', () => {
		expect(costLabel({ ...runBodyView(), metrics: { cost_usd: 0 } })).toBe('Not priced');
		expect(
			costLabel({
				...runBodyView(),
				metrics: { cost_status: 'unpriced', cost_usd: null }
			})
		).toBe('Not priced');
		expect(
			costLabel({
				...runBodyView(),
				metrics: { cost_status: 'unpriced', cost_usd: 0 }
			})
		).toBe('Not priced');
	});

	it('treats legacy payloads without cost_status as unpriced, never zero', () => {
		expect(costLabel({ ...runBodyView(), metrics: {} })).toBe('Not priced');
		expect(costStatusOf({ ...runBodyView(), metrics: {} })).toBe('unpriced');
		expect(costStatusOf({ ...runBodyView(), metrics: null })).toBe('unpriced');
		expect(costStatusOf({ ...runBodyView(), metrics: { cost_status: 'mystery' } })).toBe(
			'unpriced'
		);
	});

	it('renders a reported price when the backend sends one, end to end', () => {
		const run = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: {
				...runBody,
				metrics: { cost_status: 'reported', cost_usd: 0.42 }
			}
		}).run!;
		expect(costStatusOf(run)).toBe('reported');
		expect(costLabel(run)).toBe('$0.42');
	});

	it('never invents a price for a reported-but-null cost', () => {
		expect(
			costLabel({
				...runBodyView(),
				metrics: { cost_status: 'reported', cost_usd: null }
			})
		).toBe('Not priced');
	});
});

describe('usageLabel (measured retrieval usage)', () => {
	it('joins every measured unit into one compact honest line', () => {
		const run = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: {
				...runBody,
				metrics: {
					cost_status: 'unpriced',
					cost_usd: null,
					usage: { request_count: 37, bytes_transferred: 1257438 }
				}
			}
		}).run!;
		expect(usageLabel(run)).toBe('37 requests · 1.2 MB');
	});

	it('omits units the backend did not measure instead of showing zeros', () => {
		const bytesOnly = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: {
				...runBody,
				metrics: { usage: { request_count: null, bytes_transferred: 2048 } }
			}
		}).run!;
		expect(usageLabel(bytesOnly)).toBe('2.0 KB');

		const requestsOnly = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: {
				...runBody,
				metrics: { usage: { request_count: 12, bytes_transferred: null } }
			}
		}).run!;
		expect(usageLabel(requestsOnly)).toBe('12 requests');
	});

	it('returns nothing when nothing was measured at all', () => {
		const allNull = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: {
				...runBody,
				metrics: { usage: { request_count: null, bytes_transferred: null } }
			}
		}).run!;
		expect(usageLabel(allNull)).toBeNull();
		const noUsageKey = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: { ...runBody, metrics: { cost_status: 'unpriced', cost_usd: null } }
		}).run!;
		expect(usageLabel(noUsageKey)).toBeNull();
		expect(usageLabel({ ...runBodyView(), metrics: null })).toBeNull();
	});

	it('ignores the retired top-level flat usage fields instead of rendering them', () => {
		const flatOnly = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: {
				...runBody,
				metrics: {
					browser_wall_time_ms: 12340,
					bytes_transferred: 1257438,
					network_request_count: 37
				}
			}
		}).run!;
		expect(usageLabel(flatOnly)).toBeNull();

		const flatBesideNested = parseDiscoveryRunResponse({
			httpStatus: 200,
			body: {
				...runBody,
				metrics: {
					browser_wall_time_ms: 999_999,
					bytes_transferred: 1,
					network_request_count: 99,
					usage: { request_count: 2, bytes_transferred: 2048 }
				}
			}
		}).run!;
		expect(usageLabel(flatBesideNested)).toBe('2 requests · 2.0 KB');
	});
});

describe('latencyLabel', () => {
	it('uses an em dash for absent latency', () => {
		expect(latencyLabel(null)).toBe('—');
	});
	it('keeps sub-second latencies in milliseconds', () => {
		expect(latencyLabel(850)).toBe('850 ms');
	});
	it('humanizes seconds', () => {
		expect(latencyLabel(1250)).toBe('1.3 s');
		expect(latencyLabel(45000)).toBe('45.0 s');
	});
	it('humanizes minutes', () => {
		expect(latencyLabel(125000)).toBe('2m 5s');
	});
});

describe('tones', () => {
	it('assigns run status tones for badge coloring', () => {
		expect(runStatusTone('queued')).toBe('neutral');
		expect(runStatusTone('running')).toBe('info');
		expect(runStatusTone('succeeded')).toBe('success');
		expect(runStatusTone('partial')).toBe('warning');
		expect(runStatusTone('failed')).toBe('danger');
		expect(runStatusTone('cancelled')).toBe('danger');
	});

	it('assigns observation tones: usable is never danger unless failed', () => {
		expect(observationTone('success')).toBe('success');
		expect(observationTone('no_results')).toBe('warning');
		expect(observationTone('incomplete')).toBe('warning');
		for (const status of OBSERVATION_STATUSES) {
			if (status === 'success' || status === 'no_results' || status === 'incomplete') {
				continue;
			}
			expect(observationTone(status)).toBe('danger');
		}
	});
});

function runBodyView() {
	return parseDiscoveryRunResponse({ httpStatus: 200, body: runBody }).run!;
}
