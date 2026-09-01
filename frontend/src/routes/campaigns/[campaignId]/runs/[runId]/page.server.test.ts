import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: { API_TOKEN: 'test-token' } }));
vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'http://api.test' }
}));

import { load } from './+page.server';
import type { DiscoveryRunBody } from '$lib/discovery';

const plan = {
	source: 'prototype-smoke',
	provider_variant: 'obscura-duckduckgo-lite@2026-08-21',
	config_sha256: 'c'.repeat(64),
	document_sha256: 'd'.repeat(64),
	queries: [
		{
			id: 'q01-api-security-broad',
			pattern: null,
			query: 'API security',
			subreddits: []
		}
	]
};

function runBody(campaignId: string): DiscoveryRunBody {
	return {
		id: '6a9a2f0e-2222-4bbb-8ccc-000000000002',
		campaign_id: campaignId,
		workspace_id: '00000000-0000-0000-0000-000000000001',
		status: 'running',
		method_plan: plan,
		correlation_id: 'corr1234567890ab',
		metrics: null,
		started_at: null,
		completed_at: null,
		created_at: '2026-08-23T10:00:00Z',
		updated_at: '2026-08-23T10:00:00Z'
	};
}

function loadArgs(campaignId: string) {
	return {
		fetch: vi.fn(),
		depends: vi.fn(),
		params: {
			campaignId,
			runId: '6a9a2f0e-2222-4bbb-8ccc-000000000002'
		}
	};
}

describe('discovery run page load', () => {
	it('refuses to render another campaign\'s run under this campaign URL', async () => {
		const otherCampaignRun = runBody('6a9a2f0e-9999-4bbb-8ccc-000000000099');
		const requestFetch = vi.fn().mockResolvedValue(
			new Response(JSON.stringify(otherCampaignRun), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			})
		);

		const result = await load({
			...loadArgs('6a9a2f0e-1111-4bbb-8ccc-000000000001'),
			fetch: requestFetch
		} as never);
		if (!result) {
			throw new Error('run page load returned no data');
		}

		expect(result.runState.run).toBeNull();
		expect(result.runState.detail).toBe('Discovery run not found.');
		// A foreign run's evidence must not be fetched at all.
		expect(requestFetch).toHaveBeenCalledTimes(1);
	});

	it('loads the run and its observations when the campaign matches', async () => {
		const ownCampaignRun = runBody('6a9a2f0e-1111-4bbb-8ccc-000000000001');
		const requestFetch = vi
			.fn()
			.mockResolvedValueOnce(
				new Response(JSON.stringify(ownCampaignRun), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				})
			)
			.mockResolvedValueOnce(
				new Response(JSON.stringify({ items: [], next_cursor: null }), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				})
			)
			.mockResolvedValueOnce(
				new Response(
					JSON.stringify({
						items: [],
						expected_count: 0,
						fetched_count: 0,
						normalized_count: 0,
						processing_complete: false
					}),
					{
						status: 200,
						headers: { 'content-type': 'application/json' }
					}
				)
			);

		const result = await load({
			...loadArgs('6a9a2f0e-1111-4bbb-8ccc-000000000001'),
			fetch: requestFetch
		} as never);
		if (!result) {
			throw new Error('run page load returned no data');
		}

		expect(result.runState.run).not.toBeNull();
		expect(result.observationsState.items).toEqual([]);
		expect(requestFetch).toHaveBeenCalledTimes(3);
	});
});
