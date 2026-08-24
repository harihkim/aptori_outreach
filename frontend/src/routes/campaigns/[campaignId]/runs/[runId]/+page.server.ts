import type { PageServerLoad } from './$types';

import {
	parseDiscoveryRunResponse,
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
