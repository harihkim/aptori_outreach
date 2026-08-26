import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';

import {
	CREATE_SUBMISSION_ID,
	explainCampaignError,
	nextActions,
	parseCampaignsResponse,
	parseListLines,
	transitionSubmissionId,
	updateSubmissionId,
	type Campaign
} from '$lib/campaigns';
import { discoverySubmissionId, explainDiscoveryError } from '$lib/discovery';
import { callApi, type ApiResult } from '$lib/server/api';

function explain(result: ApiResult): string {
	if (result.status === 0) {
		return 'Backend did not answer.';
	}
	return explainCampaignError(result.status, result.body);
}

function requiredText(form: FormData, field: string): string {
	return String(form.get(field) ?? '');
}

function optionalText(form: FormData, field: string): string | null {
	const value = String(form.get(field) ?? '').trim();
	return value === '' ? null : value;
}

function lineList(form: FormData, field: string): string[] {
	return parseListLines(String(form.get(field) ?? ''));
}

/** The submission's idempotency key: reused across retries of one submission. */
function submissionKey(form: FormData): string {
	const provided = String(form.get('idempotency_key') ?? '').trim();
	return provided || crypto.randomUUID();
}

function buildSubmissionKeys(campaigns: Campaign[]): Record<string, string> {
	const keys: Record<string, string> = {
		[CREATE_SUBMISSION_ID]: crypto.randomUUID()
	};
	for (const campaign of campaigns) {
		if (campaign.status !== 'archived') {
			keys[updateSubmissionId(campaign.id)] = crypto.randomUUID();
		}
		for (const action of nextActions(campaign.status)) {
			keys[transitionSubmissionId(campaign.id, action.status)] = crypto.randomUUID();
		}
		// Discovery starts on active campaigns only; the backend still
		// enforces the truth, the key just pre-provisions the attempt.
		if (campaign.status === 'active') {
			keys[discoverySubmissionId(campaign.id)] = crypto.randomUUID();
		}
	}
	return keys;
}

/** The full editable Campaign contract, identical for create and update. */
function campaignPayload(form: FormData): Record<string, string | string[] | null> {
	return {
		name: requiredText(form, 'name'),
		product_context: optionalText(form, 'product_context'),
		icp: optionalText(form, 'icp'),
		keywords: lineList(form, 'keywords'),
		subreddits: lineList(form, 'subreddits'),
		competitors: lineList(form, 'competitors'),
		approved_claims: lineList(form, 'approved_claims'),
		prohibited_claims: lineList(form, 'prohibited_claims'),
		promotion_posture: requiredText(form, 'promotion_posture')
	};
}

export const load: PageServerLoad = async ({ fetch, depends, url }) => {
	depends('app:campaigns');

	const currentCursor = url.searchParams.get('cursor');
	const query = new URLSearchParams({ limit: '50' });
	if (currentCursor) {
		query.set('cursor', currentCursor);
	}
	const result = await callApi(fetch, 'GET', `/campaigns?${query}`, null, {
		timeoutMs: 3000
	});
	const state = parseCampaignsResponse({
		httpStatus: result.status ?? null,
		body: result.body
	});

	return {
		...state,
		currentCursor,
		submissionKeys: buildSubmissionKeys(state.campaigns)
	};
};

export const actions: Actions = {
	create: async ({ request, fetch }) => {
		const form = await request.formData();
		const key = submissionKey(form);
		const result = await callApi(fetch, 'POST', '/campaigns', campaignPayload(form), {
			write: true,
			idempotencyKey: key
		});
		if (!result.ok) {
			// The key rides back to the form so a resubmission replays
			// this attempt instead of creating a second Campaign.
			return fail(400, {
				message: explain(result),
				submission_id: CREATE_SUBMISSION_ID,
				idempotency_key: key
			});
		}
		return { created: true };
	},

	update: async ({ request, fetch }) => {
		const form = await request.formData();
		const campaignId = requiredText(form, 'campaign_id');
		const key = submissionKey(form);
		const result = await callApi(
			fetch,
			'PATCH',
			`/campaigns/${campaignId}`,
			campaignPayload(form),
			{ write: true, idempotencyKey: key }
		);
		if (!result.ok) {
			return fail(400, {
				message: explain(result),
				submission_id: updateSubmissionId(campaignId),
				idempotency_key: key
			});
		}
		return { updated: true };
	},

	transition: async ({ request, fetch }) => {
		const form = await request.formData();
		const campaignId = requiredText(form, 'campaign_id');
		const requestedStatus = requiredText(form, 'status');
		const key = submissionKey(form);
		const result = await callApi(
			fetch,
			'PATCH',
			`/campaigns/${campaignId}`,
			{ status: requestedStatus },
			{ write: true, idempotencyKey: key }
		);
		if (!result.ok) {
			return fail(400, {
				message: explain(result),
				submission_id: transitionSubmissionId(campaignId, requestedStatus),
				idempotency_key: key
			});
		}
		return { transitioned: true };
	},

	'start-discovery': async ({ request, fetch }) => {
		const form = await request.formData();
		const campaignId = requiredText(form, 'campaign_id');
		const key = submissionKey(form);
		// An empty object is the whole contract today; the backend enforces
		// that the campaign is ACTIVE regardless of what this form claims.
		const result = await callApi(
			fetch,
			'POST',
			`/campaigns/${campaignId}/discovery-runs`,
			{},
			{ write: true, idempotencyKey: key }
		);
		if (!result.ok) {
			return fail(400, {
				message:
					result.status === 0
						? 'Backend did not answer.'
						: explainDiscoveryError(result.status, result.body),
				submission_id: discoverySubmissionId(campaignId),
				idempotency_key: key
			});
		}
		const runId = (result.body as { id?: unknown } | null)?.id;
		if (typeof runId !== 'string' || !runId) {
			return fail(400, {
				message: 'Unexpected response (missing run id).',
				submission_id: discoverySubmissionId(campaignId),
				idempotency_key: key
			});
		}
		throw redirect(303, `/campaigns/${campaignId}/runs/${runId}`);
	}
};
