import { describe, expect, it, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => {
	const privateEnv: Record<string, string> = {};
	const publicEnv: Record<string, string> = {};
	return { privateEnv, publicEnv };
});

vi.mock('$env/dynamic/private', () => ({ env: mocks.privateEnv }));
vi.mock('$env/dynamic/public', () => ({ env: mocks.publicEnv }));

import { callApi, type ApiFetch } from './api';

type RecordedCall = { url: string; init: RequestInit };

function scriptedFetch(steps: Array<'network-failure' | Response>): {
	fetchMock: ApiFetch;
	calls: RecordedCall[];
} {
	const calls: RecordedCall[] = [];
	let index = 0;
	const fetchMock: ApiFetch = async (input, init) => {
		calls.push({ url: String(input), init: init ?? {} });
		const step = steps[index];
		index += 1;
		if (step === undefined) {
			throw new Error(`unexpected extra fetch #${index}`);
		}
		if (step === 'network-failure') {
			throw new TypeError('fetch failed: ECONNREFUSED');
		}
		return step;
	};
	return { fetchMock, calls };
}

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

function headersOf(call: RecordedCall): Record<string, string> {
	return call.init.headers as Record<string, string>;
}

describe('shared server-side callApi', () => {
	beforeEach(() => {
		delete mocks.privateEnv.API_TOKEN;
		delete mocks.publicEnv.PUBLIC_API_BASE_URL;
	});

	it('retries a GET exactly once on a network-level failure and recovers', async () => {
		const { fetchMock, calls } = scriptedFetch([
			'network-failure',
			jsonResponse(200, { id: 'run-1' })
		]);

		const result = await callApi(fetchMock, 'GET', '/discovery-runs/run-1', null, {
			timeoutMs: 1000
		});

		expect(result).toEqual({ ok: true, status: 200, body: { id: 'run-1' } });
		expect(calls).toHaveLength(2);
		expect(calls[0].url).toBe(calls[1].url);
	});

	it('never retries a GET the backend actually answered', async () => {
		const { fetchMock, calls } = scriptedFetch([
			jsonResponse(500, { detail: { code: 'boom' } })
		]);

		const result = await callApi(fetchMock, 'GET', '/campaigns', null, {
			timeoutMs: 1000
		});

		expect(result.ok).toBe(false);
		expect(result.status).toBe(500);
		expect(calls).toHaveLength(1);
	});

	it('never blind-retries a write even when the network failed', async () => {
		const { fetchMock, calls } = scriptedFetch(['network-failure']);

		const result = await callApi(fetchMock, 'POST', '/campaigns', {}, {
			write: true,
			idempotencyKey: 'fixed-key',
			timeoutMs: 1000
		});

		expect(result.ok).toBe(false);
		expect(result.status).toBe(0);
		expect(result.body).toBeNull();
		expect(calls).toHaveLength(1);
	});

	it('carries the bearer token and joins base URL and path byte-for-byte', async () => {
		mocks.privateEnv.API_TOKEN = 'deployment-token';
		const { fetchMock, calls } = scriptedFetch([jsonResponse(200, {})]);

		await callApi(fetchMock, 'GET', '/campaigns?limit=50', null, { timeoutMs: 1000 });

		expect(calls[0].url).toBe('http://127.0.0.1:8000/campaigns?limit=50');
		expect(headersOf(calls[0])['Authorization']).toBe('Bearer deployment-token');
	});

	it('sends no auth or idempotency headers on tokenless reads', async () => {
		const { fetchMock, calls } = scriptedFetch([jsonResponse(200, {})]);

		await callApi(fetchMock, 'GET', '/campaigns', null, { timeoutMs: 1000 });

		const headers = headersOf(calls[0]);
		expect(headers['Authorization']).toBeUndefined();
		expect(headers['Idempotency-Key']).toBeUndefined();
		expect(headers['content-type']).toBe('application/json');
	});

	it('stamps writes with the caller idempotency key and serializes the payload', async () => {
		const { fetchMock, calls } = scriptedFetch([jsonResponse(201, { id: 'c1' })]);

		await callApi(fetchMock, 'POST', '/campaigns', { name: 'Acme' }, {
			write: true,
			idempotencyKey: 'fixed-key',
			timeoutMs: 1000
		});

		expect(headersOf(calls[0])['Idempotency-Key']).toBe('fixed-key');
		expect(calls[0].init.body).toBe(JSON.stringify({ name: 'Acme' }));
		expect(headersOf(calls[0])['content-type']).toBe('application/json');
	});

	it('sends a null body when there is no payload', async () => {
		const { fetchMock, calls } = scriptedFetch([jsonResponse(200, {})]);

		await callApi(fetchMock, 'GET', '/health', null, { timeoutMs: 1000 });

		expect(calls[0].init.body).toBeNull();
	});

	it('parses non-JSON error bodies as null instead of throwing', async () => {
		const { fetchMock } = scriptedFetch([
			new Response('<html>bad gateway</html>', { status: 502 })
		]);

		const result = await callApi(fetchMock, 'GET', '/campaigns', null, {
			timeoutMs: 1000
		});

		expect(result.status).toBe(502);
		expect(result.body).toBeNull();
	});
});
