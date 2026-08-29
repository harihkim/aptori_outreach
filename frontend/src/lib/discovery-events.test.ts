import { describe, expect, it } from 'vitest';

import { parseDiscoveryEvent } from './discovery-events';

describe('parseDiscoveryEvent', () => {
	it('parses a correlated event envelope from SSE data', () => {
		expect(
			parseDiscoveryEvent(
				'discovery.candidate_found',
				JSON.stringify({
					id: 'event-1',
					type: 'discovery.candidate_found',
					run_id: 'run-1',
					workspace_id: 'workspace-1',
					correlation_id: 'corr-1',
					occurred_at: '2026-08-30T10:00:00Z',
					payload: { query_id: 'q-a', candidate: { url: 'https://reddit.com/r/x' } }
				})
			)
		).toEqual({
			type: 'discovery.candidate_found',
			id: 'event-1',
			runId: 'run-1',
			workspaceId: 'workspace-1',
			correlationId: 'corr-1',
			occurredAt: '2026-08-30T10:00:00Z',
			payload: { query_id: 'q-a', candidate: { url: 'https://reddit.com/r/x' } }
		});
	});

	it('rejects unknown event types and malformed payloads', () => {
		expect(parseDiscoveryEvent('future.event', '{}')).toBeNull();
		expect(parseDiscoveryEvent('discovery.started', '{"type":"discovery.started"}')).toBeNull();
		expect(parseDiscoveryEvent('discovery.started', 'not-json')).toBeNull();
	});

	it('rejects an envelope whose declared type differs from the SSE type', () => {
		expect(
			parseDiscoveryEvent(
				'discovery.started',
				JSON.stringify({
					id: 'event-1',
					type: 'discovery.completed',
					run_id: 'run-1',
					workspace_id: 'workspace-1',
					correlation_id: 'corr-1',
					occurred_at: '2026-08-30T10:00:00Z',
					payload: {}
				})
			)
		).toBeNull();
	});
});
