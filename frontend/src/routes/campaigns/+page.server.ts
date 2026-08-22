import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';
import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';

import {
	explainCampaignError,
	parseCampaignsResponse,
	parseClaimLines,
	parseTagInput
} from '$lib/campaigns';

const apiBaseUrl = publicEnv.PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

type ApiResult = { ok: boolean; status: number; body: unknown };

async function callApi(
	method: string,
	path: string,
	payload: unknown,
	{ write = false }: { write?: boolean } = {}
): Promise<ApiResult> {
	const headers: Record<string, string> = { 'content-type': 'application/json' };
	if (write) {
		// Writes require the deployment bearer token and a fresh idempotency
		// key; each form submission is a distinct request.
		if (env.API_TOKEN) {
			headers['Authorization'] = `Bearer ${env.API_TOKEN}`;
		}
		headers['Idempotency-Key'] = crypto.randomUUID();
	}
	try {
		const response = await fetch(`${apiBaseUrl}${path}`, {
			method,
			headers,
			body: JSON.stringify(payload),
			signal: AbortSignal.timeout(5000)
		});
		const body = await response.json().catch(() => null);
		return { ok: response.ok, status: response.status, body };
	} catch {
		return { ok: false, status: 0, body: null };
	}
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

function tagList(form: FormData, field: string): string[] {
	return parseTagInput(String(form.get(field) ?? ''));
}

function claimList(form: FormData, field: string): string[] {
	return parseClaimLines(String(form.get(field) ?? ''));
}

/** The full editable Campaign contract, identical for create and update. */
function campaignPayload(form: FormData): Record<string, string | string[] | null> {
	return {
		name: requiredText(form, 'name'),
		product_context: optionalText(form, 'product_context'),
		icp: optionalText(form, 'icp'),
		keywords: tagList(form, 'keywords'),
		subreddits: tagList(form, 'subreddits'),
		competitors: tagList(form, 'competitors'),
		approved_claims: claimList(form, 'approved_claims'),
		prohibited_claims: claimList(form, 'prohibited_claims'),
		promotion_posture: requiredText(form, 'promotion_posture')
	};
}

export const load: PageServerLoad = async ({ fetch, depends }) => {
	depends('app:campaigns');

	let httpStatus: number | null = null;
	let body: unknown = null;
	try {
		const response = await fetch(`${apiBaseUrl}/campaigns`, {
			signal: AbortSignal.timeout(3000)
		});
		httpStatus = response.status;
		body = await response.json().catch(() => null);
	} catch {
		httpStatus = null;
	}

	return parseCampaignsResponse({ httpStatus, body });
};

export const actions: Actions = {
	create: async ({ request }) => {
		const form = await request.formData();
		const result = await callApi('POST', '/campaigns', campaignPayload(form), { write: true });
		if (!result.ok) {
			return fail(400, { message: explain(result) });
		}
		return { created: true };
	},

	update: async ({ request }) => {
		const form = await request.formData();
		const result = await callApi(
			'PATCH',
			`/campaigns/${requiredText(form, 'campaign_id')}`,
			campaignPayload(form),
			{ write: true }
		);
		if (!result.ok) {
			return fail(400, { message: explain(result) });
		}
		return { updated: true };
	},

	transition: async ({ request }) => {
		const form = await request.formData();
		const result = await callApi(
			'PATCH',
			`/campaigns/${requiredText(form, 'campaign_id')}`,
			{ status: requiredText(form, 'status') },
			{ write: true }
		);
		if (!result.ok) {
			return fail(400, { message: explain(result) });
		}
		return { transitioned: true };
	}
};
