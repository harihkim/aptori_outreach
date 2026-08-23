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

describe('start-discovery action', () => {
	function discoveryRequest(key: string): Request {
		const form = new FormData();
		form.set('campaign_id', 'campaign-1');
		form.set('submission_id', `discovery:campaign-1`);
		form.set('idempotency_key', key);
		return new Request('http://app.test/campaigns?/start-discovery', {
			method: 'POST',
			body: form
		});
	}

	it('redirects to the run screen when the backend queues the run', async () => {
		const requestFetch = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ id: 'run-123', status: 'queued' }), {
				status: 201,
				headers: { 'content-type': 'application/json' }
			})
		);
		const startDiscovery = actions['start-discovery'];
		if (startDiscovery === undefined) {
			throw new Error('start-discovery action is not registered');
		}

		const outcome = startDiscovery({
			request: discoveryRequest('discovery-key'),
			fetch: requestFetch
		} as never);

		await expect(outcome).rejects.toMatchObject({
			status: 303,
			location: '/campaigns/campaign-1/runs/run-123'
		});
		const call = requestFetch.mock.calls[0];
		expect(call[0]).toBe('http://api.test/campaigns/campaign-1/discovery-runs');
		const headers = new Headers(call[1]?.headers);
		expect(headers.get('Idempotency-Key')).toBe('discovery-key');
	});

	it('explains a non-active campaign instead of navigating', async () => {
		const requestFetch = vi.fn().mockResolvedValue(
			new Response(
				JSON.stringify({
					detail: { code: 'campaign_not_active', message: 'Campaign is draft.' }
				}),
				{ status: 409, headers: { 'content-type': 'application/json' } }
			)
		);

		const result = (await actions['start-discovery']?.({
			request: discoveryRequest('failed-discovery-key'),
			fetch: requestFetch
		} as never)) as { status?: number; data?: Record<string, unknown> } | undefined;
		if (!result || !result.data) {
			throw new Error('expected a fail() result');
		}

		expect(result.status).toBe(400);
		expect(result.data.message).toBe('Only ACTIVE campaigns can run discovery.');
		expect(result.data.submission_id).toBe('discovery:campaign-1');
		expect(result.data.idempotency_key).toBe('failed-discovery-key');
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

		const result = await load({
			fetch: requestFetch,
			depends: vi.fn(),
			url: new URL('http://app.test/campaigns')
		} as never);
		if (!result) {
			throw new Error('campaign page load returned no data');
		}

		expect(result.detail).toBe('The backend has no API token configured.');
		expect(result.campaigns).toEqual([]);
	});

	it('passes an opaque cursor through to the bounded backend listing', async () => {
		const requestFetch = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ items: [], next_cursor: null }), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			})
		);

		const result = await load({
			fetch: requestFetch,
			depends: vi.fn(),
			url: new URL('http://app.test/campaigns?cursor=older-page')
		} as never);

		expect(result && result.currentCursor).toBe('older-page');
		expect(requestFetch).toHaveBeenCalledWith(
			'http://api.test/campaigns?limit=50&cursor=older-page',
			expect.any(Object)
		);
	});
});
