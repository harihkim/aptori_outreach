import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';
import type { PageServerLoad } from './$types';

import {
	parseDiscoveryRunResponse,
	parseObservationsResponse
} from '$lib/discovery';

const apiBaseUrl = publicEnv.PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

type ApiResult = { ok: boolean; status: number; body: unknown };
type ApiFetch = (
	input: string | URL | Request,
	init?: RequestInit
) => Promise<Response>;

async function callApi(
	requestFetch: ApiFetch,
	method: string,
	path: string,
	payload: unknown,
	{
		write = false,
		timeoutMs = 5000,
		idempotencyKey = crypto.randomUUID()
	}: { write?: boolean; timeoutMs?: number; idempotencyKey?: string } = {}
): Promise<ApiResult> {
	const headers: Record<string, string> = { 'content-type': 'application/json' };
	// Every request carries the deployment bearer token when configured;
	// reads never carry an idempotency key because they cannot duplicate work.
	if (env.API_TOKEN) {
		headers['Authorization'] = `Bearer ${env.API_TOKEN}`;
	}
	if (write) {
		headers['Idempotency-Key'] = idempotencyKey;
	}

	async function attempt(): Promise<ApiResult> {
		try {
			const response = await requestFetch(`${apiBaseUrl}${path}`, {
				method,
				headers,
				body: payload === null ? null : JSON.stringify(payload),
				signal: AbortSignal.timeout(timeoutMs)
			});
			const body = await response.json().catch(() => null);
			return { ok: response.ok, status: response.status, body };
		} catch {
			return { ok: false, status: 0, body: null };
		}
	}

	const first = await attempt();
	// One blind retry when the network failed: every request on this page is
	// a read, so repeating it can never duplicate work.
	if (!first.ok && first.status === 0) {
		return attempt();
	}
	return first;
}

export const load: PageServerLoad = async ({ fetch, depends, params }) => {
	depends('app:discovery-run');

	const runResult = await callApi(
		fetch,
		'GET',
		`/discovery-runs/${params.runId}`,
		null,
		{ timeoutMs: 3000 }
	);
	const runState = parseDiscoveryRunResponse({
		httpStatus: runResult.status || null,
		body: runResult.body
	});

	// The URL names the campaign too; a run belonging to another campaign
	// must never render here as if it were this campaign's run.
	if (runState.run && String(runState.run.campaignId) !== params.campaignId) {
		return {
			runState: { apiReachable: true, run: null, detail: 'Discovery run not found.' },
			observationsState: {
				apiReachable: false,
				items: [],
				nextCursor: null,
				detail: 'Discovery run not found.'
			},
			params: { campaignId: params.campaignId, runId: params.runId }
		};
	}

	const observationsResult = await callApi(
		fetch,
		'GET',
		`/discovery-runs/${params.runId}/observations?limit=100`,
		null,
		{ timeoutMs: 3000 }
	);
	const observationsState = parseObservationsResponse({
		httpStatus: observationsResult.status || null,
		body: observationsResult.body
	});

	return {
		runState,
		observationsState,
		params: { campaignId: params.campaignId, runId: params.runId }
	};
};
