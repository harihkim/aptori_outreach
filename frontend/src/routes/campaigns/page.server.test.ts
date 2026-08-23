import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: { API_TOKEN: 'test-token' } }));
vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'http://api.test' }
}));

import { actions, load } from './+page.server';
import { CREATE_SUBMISSION_ID } from '$lib/campaigns';

function createRequest(key: string): Request {
	const form = new FormData();
	form.set('submission_id', CREATE_SUBMISSION_ID);
	form.set('idempotency_key', key);
	form.set('name', 'API security listening');
	form.set('promotion_posture', 'expertise_first');
	return new Request('http://app.test/campaigns?/create', {
		method: 'POST',
		body: form
	});
}

describe('campaign create action', () => {
	it('retries one network failure with the same form-scoped key', async () => {
		const requestFetch = vi
			.fn()
			.mockRejectedValueOnce(new TypeError('connection reset'))
			.mockResolvedValueOnce(
				new Response('{}', {
					status: 201,
					headers: { 'content-type': 'application/json' }
				})
			);
		const create = actions.create;
		if (create === undefined) {
			throw new Error('create action is not registered');
		}

		const result = await create({
			request: createRequest('stable-create-key'),
			fetch: requestFetch
		} as never);

		expect(result).toEqual({ created: true });
		expect(requestFetch).toHaveBeenCalledTimes(2);
		for (const call of requestFetch.mock.calls) {
			const headers = new Headers(call[1]?.headers);
			expect(headers.get('Idempotency-Key')).toBe('stable-create-key');
		}
	});
});

describe('campaign page load', () => {
	it('surfaces stable backend configuration guidance', async () => {
		const requestFetch = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ detail: { code: 'api_token_unconfigured' } }), {
				status: 503,
				headers: { 'content-type': 'application/json' }
			})
		);

		const result = await load({ fetch: requestFetch, depends: vi.fn() } as never);
		if (!result) {
			throw new Error('campaign page load returned no data');
		}

		expect(result.detail).toBe('The backend has no API token configured.');
		expect(result.campaigns).toEqual([]);
	});
});
