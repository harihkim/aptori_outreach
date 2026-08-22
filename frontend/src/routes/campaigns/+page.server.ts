import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';
import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';

import {
	explainCampaignError,
	parseCampaignsResponse,
	parseListLines
} from '$lib/campaigns';

const apiBaseUrl = publicEnv.PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

type ApiResult = { ok: boolean; status: number; body: unknown };

async function callApi(
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
			const response = await fetch(`${apiBaseUrl}${path}`, {
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

	const result = await callApi('GET', '/campaigns', null, { timeoutMs: 3000 });

	return parseCampaignsResponse({ httpStatus: result.status || null, body: result.body });
};

export const actions: Actions = {
	create: async ({ request }) => {
		const form = await request.formData();
		const key = submissionKey(form);
		const result = await callApi('POST', '/campaigns', campaignPayload(form), {
			write: true,
			idempotencyKey: key
		});
		if (!result.ok) {
			// The key rides back to the form so a resubmission replays
			// this attempt instead of creating a second Campaign.
			return fail(400, { message: explain(result), idempotency_key: key });
		}
		return { created: true };
	},

	update: async ({ request }) => {
		const form = await request.formData();
		const key = submissionKey(form);
		const result = await callApi(
			'PATCH',
			`/campaigns/${requiredText(form, 'campaign_id')}`,
			campaignPayload(form),
			{ write: true, idempotencyKey: key }
		);
		if (!result.ok) {
			return fail(400, { message: explain(result), idempotency_key: key });
		}
		return { updated: true };
	},

	transition: async ({ request }) => {
		const form = await request.formData();
		const key = submissionKey(form);
		const result = await callApi(
			'PATCH',
			`/campaigns/${requiredText(form, 'campaign_id')}`,
			{ status: requiredText(form, 'status') },
			{ write: true, idempotencyKey: key }
		);
		if (!result.ok) {
			return fail(400, { message: explain(result), idempotency_key: key });
		}
		return { transitioned: true };
	}
};
