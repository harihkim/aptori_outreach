import { describe, expect, it } from 'vitest';

import { parseHealthContract, type HealthBody } from '$lib/health';

const healthyBody: HealthBody = {
	status: 'ok',
	api: 'reachable',
	database: 'ok',
	detail: null
};

describe('parseHealthContract', () => {
	it('reports operational only for the complete healthy contract', () => {
		const state = parseHealthContract({
			httpStatus: 200,
			body: healthyBody,
			apiBaseUrl: 'http://127.0.0.1:8000'
		});

		expect(state).toEqual({
			apiReachable: true,
			database: 'ok',
			degraded: false,
			apiBaseUrl: 'http://127.0.0.1:8000',
			detail: null
		});
	});

	it('treats a missing healthy field as degraded even if the rest claim ok', () => {
		const state = parseHealthContract({
			httpStatus: 200,
			body: { status: 'ok', database: 'ok' },
			apiBaseUrl: 'http://127.0.0.1:8000'
		});

		expect(state.degraded).toBe(true);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('maps a 503 degraded body to database unavailable with its detail', () => {
		const state = parseHealthContract({
			httpStatus: 503,
			body: {
				status: 'degraded',
				api: 'reachable',
				database: 'unavailable',
				detail: 'database unavailable'
			},
			apiBaseUrl: 'http://127.0.0.1:8000'
		});

		expect(state).toEqual({
			apiReachable: true,
			database: 'unavailable',
			degraded: true,
			apiBaseUrl: 'http://127.0.0.1:8000',
			detail: 'database unavailable'
		});
	});

	it('reports database unknown when the body does not claim unavailable', () => {
		const state = parseHealthContract({
			httpStatus: 500,
			body: { status: 'degraded', database: 'ok' },
			apiBaseUrl: 'http://127.0.0.1:8000'
		});

		expect(state.apiReachable).toBe(true);
		expect(state.database).toBe('unknown');
	});

	it('reports unreachable when the request never completed', () => {
		const state = parseHealthContract({
			httpStatus: null,
			body: null,
			apiBaseUrl: 'http://127.0.0.1:8000'
		});

		expect(state).toEqual({
			apiReachable: false,
			database: 'unknown',
			degraded: true,
			apiBaseUrl: 'http://127.0.0.1:8000',
			detail: 'Backend did not answer'
		});
	});

	it('treats an unparseable body as an unexpected response', () => {
		const state = parseHealthContract({
			httpStatus: 200,
			body: null,
			apiBaseUrl: 'http://127.0.0.1:8000'
		});

		expect(state.degraded).toBe(true);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});
});
