import type { PageServerLoad } from './$types';

import { parseCampaignsResponse } from '$lib/campaigns';
import { OPPORTUNITY_STATUSES, parseOpportunitiesResponse } from '$lib/opportunities';
import { callApi } from '$lib/server/api';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const load: PageServerLoad = async ({ fetch, depends, url }) => {
	depends('app:opportunities');

	// Filters ride in the URL so a triage view is shareable and reload-safe.
	// Anything unrecognised falls back to the default rather than reaching
	// the backend as a malformed query.
	const requestedStatus = url.searchParams.get('status') ?? 'open';
	const status = (OPPORTUNITY_STATUSES as readonly string[]).includes(requestedStatus)
		? requestedStatus
		: 'open';
	const requestedCampaign = url.searchParams.get('campaign');
	const campaignId =
		requestedCampaign && UUID_PATTERN.test(requestedCampaign) ? requestedCampaign : null;

	const query = new URLSearchParams({ limit: '100', status });
	if (campaignId) {
		query.set('campaign_id', campaignId);
	}
	const [opportunitiesResult, campaignsResult] = await Promise.all([
		callApi(fetch, 'GET', `/opportunities?${query}`, null, { timeoutMs: 3000 }),
		callApi(fetch, 'GET', '/campaigns?limit=100', null, { timeoutMs: 3000 })
	]);
	const opportunitiesState = parseOpportunitiesResponse({
		httpStatus: opportunitiesResult.status ?? null,
		body: opportunitiesResult.body
	});
	const campaignsState = parseCampaignsResponse({
		httpStatus: campaignsResult.status ?? null,
		body: campaignsResult.body
	});
	const campaignNames: Record<string, string> = {};
	for (const campaign of campaignsState.campaigns) {
		campaignNames[campaign.id] = campaign.name;
	}

	return {
		opportunitiesState,
		campaignNames,
		filters: { status, campaignId }
	};
};
