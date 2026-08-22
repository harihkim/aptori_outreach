import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';
import { fail } from '@sveltejs/kit';
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
	// writes carry the caller's idempotency key so a retry of the same
	// submission replays the original result instead of duplicating it.
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
	// One same-key retry when the network failed: the write may have landed,
	// and the key makes the retry safe either way.
	if (write && !first.ok && first.status === 0) {
		return attempt();
	}
	return first;
}

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

export const load: PageServerLoad = async ({ fetch, depends }) => {
	depends('app:campaigns');

	const result = await callApi(fetch, 'GET', '/campaigns', null, { timeoutMs: 3000 });
	const state = parseCampaignsResponse({
		httpStatus: result.status || null,
		body: result.body
	});

	return { ...state, submissionKeys: buildSubmissionKeys(state.campaigns) };
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
	}
};
