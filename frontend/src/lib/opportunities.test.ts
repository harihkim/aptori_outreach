import { describe, expect, it } from 'vitest';

import {
	actionLabel,
	ageLabel,
	parseOpportunitiesResponse,
	scoreLabel,
	statusLabel
} from './opportunities';

export function opportunityBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		id: '7a9a2f0e-4444-4bbb-8ccc-000000000004',
		campaign_id: '6a9a2f0e-1111-4bbb-8ccc-000000000001',
		conversation_id: '7a9a2f0e-5555-4bbb-8ccc-000000000005',
		analysis_id: '7a9a2f0e-6666-4bbb-8ccc-000000000006',
		opportunity_score: 0.876875,
		formula_version: 'v1.0',
		score_components: { formula_version: 'v1.0', age_hours: 0 },
		status: 'open',
		post_created_at: '2026-09-01T10:00:00Z',
		scored_at: '2026-09-02T10:00:00Z',
		saved_at: null,
		dismissed_at: null,
		dismissal_reason: null,
		created_at: '2026-09-02T10:00:00Z',
		updated_at: '2026-09-02T10:00:00Z',
		conversation: {
			id: '7a9a2f0e-5555-4bbb-8ccc-000000000005',
			source_platform: 'reddit',
			canonical_external_discussion_id: 't3_rotation',
			conversation_version_id: '7a9a2f0e-7777-4bbb-8ccc-000000000007',
			normalizer_version: 'reddit-thread/v1',
			title: 'Token rotation keeps failing',
			subreddit: 'r/netsec',
			url: 'https://www.reddit.com/r/netsec/comments/x/rotation/',
			post_score: 42,
			reported_comment_count: 3
		},
		analysis: {
			id: '7a9a2f0e-6666-4bbb-8ccc-000000000006',
			analysis_identity: 'analyze_conversation@1:2026-09-02.1:1',
			factors: {
				relevance: 0.94,
				pain_intensity: 0.82,
				buying_intent: 0.71,
				replyability: 0.91,
				product_fit: 0.89,
				promotion_fit: 0.34,
				confidence: 0.8
			},
			topic: 'API auth failures',
			persona: 'security engineer',
			recommended_action: 'reply_helpfully',
			rationale: 'Direct problem fit, but the author did not ask for vendors.',
			created_at: '2026-09-02T10:00:00Z'
		},
		model_run: {
			id: '7a9a2f0e-8888-4bbb-8ccc-000000000008',
			task_id: 'analyze_conversation',
			task_version: '1',
			prompt_version: '2026-09-02.1',
			schema_version: '1',
			model_tier: 'ordinary',
			served_tier: 'ordinary',
			requested_model: 'configured-model',
			actual_model: 'configured-model-2026',
			endpoint_label: 'llm.example.test',
			input_tokens: 812,
			output_tokens: 96,
			request_count: 1,
			output_retry_count: 0,
			cost_status: 'unpriced',
			status: 'succeeded',
			created_at: '2026-09-02T10:00:00Z'
		},
		...overrides
	};
}

describe('parseOpportunitiesResponse', () => {
	it('maps the ranked wire contract into camelCase state', () => {
		const state = parseOpportunitiesResponse({
			httpStatus: 200,
			body: { items: [opportunityBody()] }
		});
		expect(state.apiReachable).toBe(true);
		expect(state.detail).toBeNull();
		expect(state.items).toHaveLength(1);
		const item = state.items[0];
		expect(item.opportunityScore).toBe(0.876875);
		expect(item.status).toBe('open');
		expect(item.conversation.title).toBe('Token rotation keeps failing');
		expect(item.conversation.url).toBe('https://www.reddit.com/r/netsec/comments/x/rotation/');
		expect(item.analysis.factors.promotion_fit).toBe(0.34);
		expect(item.analysis.recommendedAction).toBe('reply_helpfully');
		expect(item.modelRun.actualModel).toBe('configured-model-2026');
		expect(item.modelRun.endpointLabel).toBe('llm.example.test');
	});

	it('rejects the whole page when one row carries an out-of-range factor', () => {
		const bad = opportunityBody();
		const analysis = bad.analysis as Record<string, unknown>;
		bad.analysis = {
			...analysis,
			factors: { ...(analysis.factors as Record<string, number>), relevance: 1.5 }
		};
		const state = parseOpportunitiesResponse({
			httpStatus: 200,
			body: { items: [opportunityBody(), bad] }
		});
		expect(state.items).toEqual([]);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('rejects unknown recommended actions and statuses', () => {
		expect(
			parseOpportunitiesResponse({
				httpStatus: 200,
				body: { items: [opportunityBody({ status: 'archived' })] }
			}).detail
		).toBe('Unexpected response (HTTP 200)');
		const badAction = opportunityBody();
		badAction.analysis = {
			...(badAction.analysis as Record<string, unknown>),
			recommended_action: 'buy_now'
		};
		expect(
			parseOpportunitiesResponse({ httpStatus: 200, body: { items: [badAction] } }).detail
		).toBe('Unexpected response (HTTP 200)');
	});

	it('distinguishes an unreachable backend from a backend error', () => {
		expect(parseOpportunitiesResponse({ httpStatus: null, body: null })).toEqual({
			apiReachable: false,
			items: [],
			detail: 'Backend did not answer'
		});
		const denied = parseOpportunitiesResponse({
			httpStatus: 401,
			body: { detail: { code: 'unauthorized' } }
		});
		expect(denied.apiReachable).toBe(true);
		expect(denied.detail).toBe('The backend rejected the request token.');
		expect(
			parseOpportunitiesResponse({
				httpStatus: 404,
				body: { detail: { code: 'opportunity_not_found' } }
			}).detail
		).toBe('Opportunity not found.');
	});

	it('accepts an empty inbox', () => {
		expect(parseOpportunitiesResponse({ httpStatus: 200, body: { items: [] } })).toEqual({
			apiReachable: true,
			items: [],
			detail: null
		});
	});
});

describe('labels', () => {
	it('renders scores with two decimals without rounding up to 1.00', () => {
		expect(scoreLabel(0.876875)).toBe('0.87');
		expect(scoreLabel(0.999)).toBe('0.99');
		expect(scoreLabel(1)).toBe('1.00');
		expect(scoreLabel(0)).toBe('0.00');
	});

	it('describes post age in the units the decay works in', () => {
		const now = new Date('2026-09-02T12:00:00Z');
		expect(ageLabel('2026-09-02T11:30:00Z', now)).toBe('under an hour old');
		expect(ageLabel('2026-09-02T04:15:00Z', now)).toBe('7h old');
		expect(ageLabel('2026-08-30T12:00:00Z', now)).toBe('3d old');
		expect(ageLabel('not a date', now)).toBe('age unknown');
		expect(ageLabel('2026-09-03T12:00:00Z', now)).toBe('under an hour old');
	});

	it('names actions and statuses for operators', () => {
		expect(actionLabel('reply_with_product')).toBe('Reply with product');
		expect(actionLabel('content_opportunity')).toBe('Content opportunity');
		expect(statusLabel('acted_on')).toBe('Acted on');
	});
});
