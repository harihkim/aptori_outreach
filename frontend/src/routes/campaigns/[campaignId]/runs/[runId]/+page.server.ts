import type { PageServerLoad } from './$types';

import {
	parseDiscoveryRunResponse,
	parseConversationsResponse,
	parseObservationsResponse
} from '$lib/discovery';
import { callApi } from '$lib/server/api';

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
		httpStatus: runResult.status ?? null,
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
			conversationsState: {
				apiReachable: false,
				items: [],
				expectedCount: 0,
				fetchedCount: 0,
				normalizedCount: 0,
				processingComplete: false,
				detail: 'Discovery run not found.'
			},
			params: { campaignId: params.campaignId, runId: params.runId }
		};
	}

	// Independent reads; fetch them together so a slow one does not stack
	// its timeout on top of the other's.
	const [observationsResult, conversationsResult] = await Promise.all([
		callApi(fetch, 'GET', `/discovery-runs/${params.runId}/observations?limit=100`, null, {
			timeoutMs: 3000
		}),
		callApi(fetch, 'GET', `/discovery-runs/${params.runId}/conversations`, null, {
			timeoutMs: 3000
		})
	]);
	const observationsState = parseObservationsResponse({
		httpStatus: observationsResult.status ?? null,
		body: observationsResult.body
	});
	const conversationsState = parseConversationsResponse({
		httpStatus: conversationsResult.status ?? null,
		body: conversationsResult.body
	});

	return {
		runState,
		observationsState,
		conversationsState,
		params: { campaignId: params.campaignId, runId: params.runId }
	};
};
