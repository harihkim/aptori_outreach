import { env } from '$env/dynamic/public';
import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';

import { explainCampaignError, parseCampaignsResponse, parseTagInput } from '$lib/campaigns';

const apiBaseUrl = env.PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

type ApiResult = { ok: boolean; status: number; body: unknown };

async function callApi(method: string, path: string, payload: unknown): Promise<ApiResult> {
	try {
		const response = await fetch(`${apiBaseUrl}${path}`, {
			method,
			headers: { 'content-type': 'application/json' },
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
		const result = await callApi('POST', '/campaigns', {
			name: requiredText(form, 'name'),
			product_context: optionalText(form, 'product_context'),
			icp: optionalText(form, 'icp'),
			keywords: tagList(form, 'keywords'),
			subreddits: tagList(form, 'subreddits'),
			competitors: tagList(form, 'competitors'),
			promotion_posture: requiredText(form, 'promotion_posture')
		});
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
			{
				name: requiredText(form, 'name'),
				product_context: optionalText(form, 'product_context'),
				icp: optionalText(form, 'icp'),
				keywords: tagList(form, 'keywords'),
				subreddits: tagList(form, 'subreddits'),
				competitors: tagList(form, 'competitors'),
				promotion_posture: requiredText(form, 'promotion_posture')
			}
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
			{ status: requiredText(form, 'status') }
		);
		if (!result.ok) {
			return fail(400, { message: explain(result) });
		}
		return { transitioned: true };
	}
};
