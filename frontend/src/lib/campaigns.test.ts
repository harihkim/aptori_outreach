import { describe, expect, it } from 'vitest';

import {
	explainCampaignError,
	nextActions,
	parseCampaignsResponse,
	parseListLines,
	type CampaignBody
} from '$lib/campaigns';

const campaignBody: CampaignBody = {
	id: '6a9a2f0e-1111-4bbb-8ccc-000000000001',
	workspace_id: '00000000-0000-0000-0000-000000000001',
	name: 'API security listening',
	product_context: 'Aptori finds broken authorization in APIs',
	icp: 'Security engineers',
	keywords: ['API security', 'pentest'],
	subreddits: ['cybersecurity'],
	competitors: ['Burp Suite'],
	approved_claims: ['Aptori runs in CI'],
	prohibited_claims: [],
	promotion_posture: 'expertise_first',
	status: 'draft',
	created_at: '2026-08-22T10:00:00Z',
	updated_at: '2026-08-22T10:00:00Z',
	archived_at: null
};

describe('parseCampaignsResponse', () => {
	it('maps a complete listing into camelCase campaigns', () => {
		const state = parseCampaignsResponse({
			httpStatus: 200,
			body: [campaignBody]
		});

		expect(state).toEqual({
			apiReachable: true,
			campaigns: [
				{
					id: campaignBody.id,
					name: 'API security listening',
					status: 'draft',
					promotionPosture: 'expertise_first',
					productContext: 'Aptori finds broken authorization in APIs',
					icp: 'Security engineers',
					keywords: ['API security', 'pentest'],
					subreddits: ['cybersecurity'],
					competitors: ['Burp Suite'],
					approvedClaims: ['Aptori runs in CI'],
					prohibitedClaims: [],
					createdAt: '2026-08-22T10:00:00Z',
					archivedAt: null
				}
			],
			detail: null
		});
	});

	it('treats an absent list field as an unexpected response', () => {
		const state = parseCampaignsResponse({
			httpStatus: 200,
			body: [{ ...campaignBody, keywords: undefined }]
		});

		expect(state.campaigns).toEqual([]);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('treats a missing workspace id or updated_at as an unexpected response', () => {
		const noWorkspace = parseCampaignsResponse({
			httpStatus: 200,
			body: [{ ...campaignBody, workspace_id: undefined }]
		});
		const noUpdated = parseCampaignsResponse({
			httpStatus: 200,
			body: [{ ...campaignBody, updated_at: undefined }]
		});

		expect(noWorkspace.campaigns).toEqual([]);
		expect(noUpdated.campaigns).toEqual([]);
	});

	it('treats an entry with an unknown status as an unexpected response', () => {
		const state = parseCampaignsResponse({
			httpStatus: 200,
			body: [{ ...campaignBody, status: 'zombie' }]
		});

		expect(state.campaigns).toEqual([]);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('treats a non-string list item as an unexpected response', () => {
		const state = parseCampaignsResponse({
			httpStatus: 200,
			body: [{ ...campaignBody, keywords: ['API security', 5] }]
		});

		expect(state.campaigns).toEqual([]);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('treats a non-array body as an unexpected response', () => {
		const state = parseCampaignsResponse({ httpStatus: 200, body: { no: 'list' } });

		expect(state.campaigns).toEqual([]);
		expect(state.detail).toBe('Unexpected response (HTTP 200)');
	});

	it('reports unreachable when the request never completed', () => {
		const state = parseCampaignsResponse({ httpStatus: null, body: null });

		expect(state).toEqual({
			apiReachable: false,
			campaigns: [],
			detail: 'Backend did not answer'
		});
	});
});

describe('nextActions', () => {
	it('offers only legal transitions for each status', () => {
		expect(nextActions('draft')).toEqual([{ status: 'active', label: 'Activate' }]);
		expect(nextActions('active')).toEqual([
			{ status: 'paused', label: 'Pause' },
			{ status: 'archived', label: 'Archive' }
		]);
		expect(nextActions('paused')).toEqual([
			{ status: 'active', label: 'Resume' },
			{ status: 'archived', label: 'Archive' }
		]);
	});

	it('offers nothing for archived campaigns', () => {
		expect(nextActions('archived')).toEqual([]);
	});
});



describe('explainCampaignError', () => {
	it('translates stable backend error codes into operator guidance', () => {
		expect(
			explainCampaignError(409, {
				detail: { code: 'campaign_invalid_transition', message: 'draft -> paused' }
			})
		).toBe('That lifecycle change is not allowed.');

		expect(
			explainCampaignError(409, {
				detail: { code: 'campaign_archived', message: 'read-only' }
			})
		).toBe('Archived campaigns are read-only.');

		expect(
			explainCampaignError(404, { detail: { code: 'campaign_not_found', message: '' } })
		).toBe('Campaign not found.');
	});

	it('guides operators through the new auth and idempotency errors', () => {
		expect(explainCampaignError(401, { detail: { code: 'unauthorized' } })).toBe(
			'The backend rejected the request token.'
		);
		expect(
			explainCampaignError(503, { detail: { code: 'api_token_unconfigured' } })
		).toBe('The backend has no API token configured.');
		expect(
			explainCampaignError(503, { detail: { code: 'workspace_unconfigured' } })
		).toBe('The backend database needs its migrations run.');
		expect(
			explainCampaignError(400, { detail: { code: 'idempotency_key_required' } })
		).toBe('The form lost its submission key; refresh and try again.');
		expect(
			explainCampaignError(409, { detail: { code: 'idempotency_key_conflict' } })
		).toBe('This submission key was already used for different content.');
	});

	it('falls back to a generic message for unknown failures', () => {
		expect(explainCampaignError(422, { detail: [] })).toBe('Some fields were invalid.');
		expect(explainCampaignError(500, null)).toBe('Unexpected error (HTTP 500).');
	});
});

describe('parseListLines', () => {
	it('splits list input on lines and keeps commas inside a value', () => {
		expect(parseListLines('Acme, Inc.\nBurp Suite \n')).toEqual([
			'Acme, Inc.',
			'Burp Suite'
		]);
	});

	it('returns an empty list for blank input', () => {
		expect(parseListLines('  ')).toEqual([]);
	});
});
