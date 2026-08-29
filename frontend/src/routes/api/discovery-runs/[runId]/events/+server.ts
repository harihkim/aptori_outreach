import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

import { getApiBaseUrl } from '$lib/server/api';

/**
 * Keep the backend bearer token on the SvelteKit server. Browser EventSource
 * cannot set Authorization headers, so the run page connects to this same-
 * origin proxy instead of learning the deployment credential.
 */
export const GET: RequestHandler = async ({ fetch, params, request }) => {
	const headers = new Headers();
	if (env.API_TOKEN) {
		headers.set('Authorization', `Bearer ${env.API_TOKEN}`);
	}

	try {
		const upstream = await fetch(
			`${getApiBaseUrl()}/discovery-runs/${params.runId}/events`,
			{ headers, signal: request.signal }
		);
		const responseHeaders = new Headers();
		const contentType = upstream.headers.get('content-type');
		if (contentType) {
			responseHeaders.set('content-type', contentType);
		}
		responseHeaders.set('cache-control', 'no-cache, no-transform');
		responseHeaders.set('x-accel-buffering', 'no');
		return new Response(upstream.body, {
			status: upstream.status,
			statusText: upstream.statusText,
			headers: responseHeaders
		});
	} catch {
		return new Response(null, {
			status: 503,
			headers: { 'cache-control': 'no-store' }
		});
	}
};
