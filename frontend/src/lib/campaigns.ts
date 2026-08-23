export const CAMPAIGN_STATUSES = ['draft', 'active', 'paused', 'archived'] as const;
export const CAMPAIGN_POSTURES = [
	'expertise_first',
	'balanced',
	'high_intent_only'
] as const;

export type CampaignStatus = (typeof CAMPAIGN_STATUSES)[number];
export type PromotionPosture = (typeof CAMPAIGN_POSTURES)[number];

export const DEFAULT_PROMOTION_POSTURE: PromotionPosture = 'expertise_first';

export type CampaignBody = {
	id: string;
	workspace_id: string;
	name: string;
	product_context: string | null;
	icp: string | null;
	keywords: string[];
	subreddits: string[];
	competitors: string[];
	approved_claims: string[];
	prohibited_claims: string[];
	promotion_posture: string;
	status: string;
	created_at: string;
	updated_at: string;
	archived_at: string | null;
};

export type Campaign = {
	id: string;
	name: string;
	status: CampaignStatus;
	promotionPosture: PromotionPosture;
	productContext: string | null;
	icp: string | null;
	keywords: string[];
	subreddits: string[];
	competitors: string[];
	approvedClaims: string[];
	prohibitedClaims: string[];
	createdAt: string;
	updatedAt: string;
	archivedAt: string | null;
};

export type CampaignsState = {
	/** The backend answered our request, whatever it said. */
	apiReachable: boolean;
	campaigns: Campaign[];
	nextCursor: string | null;
	detail: string | null;
};

export type LifecycleAction = { status: CampaignStatus; label: string };

export const CREATE_SUBMISSION_ID = 'create';

export function updateSubmissionId(campaignId: string): string {
	return `update:${campaignId}`;
}

export function transitionSubmissionId(
	campaignId: string,
	status: string
): string {
	return `transition:${campaignId}:${status}`;
}

function isCampaignStatus(value: string): value is CampaignStatus {
	return (CAMPAIGN_STATUSES as readonly string[]).includes(value);
}

function isPromotionPosture(value: string): value is PromotionPosture {
	return (CAMPAIGN_POSTURES as readonly string[]).includes(value);
}

const LIST_FIELDS = ['keywords', 'subreddits', 'competitors', 'approved_claims', 'prohibited_claims'] as const;

function isStringList(value: unknown): value is string[] {
	return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

/** The wire shape after validation: status and posture are known-good. */
type ValidatedCampaignBody = Omit<CampaignBody, 'status' | 'promotion_posture'> & {
	status: CampaignStatus;
	promotion_posture: PromotionPosture;
};

/**
 * Derive the Campaigns list state from one backend response.
 *
 * `httpStatus` is null when the request never completed (network error or
 * timeout); `body` is unknown because the backend may answer with anything.
 * The listing is trusted only when every entry carries the complete contract.
 */
export function parseCampaignsResponse({
	httpStatus,
	body
}: {
	httpStatus: number | null;
	body: unknown;
}): CampaignsState {
	if (httpStatus === null) {
		return {
			apiReachable: false,
			campaigns: [],
			nextCursor: null,
			detail: 'Backend did not answer'
		};
	}

	const unexpected: CampaignsState = {
		apiReachable: true,
		campaigns: [],
		nextCursor: null,
		detail: `Unexpected response (HTTP ${httpStatus})`
	};

	if (httpStatus !== 200) {
		return { ...unexpected, detail: explainCampaignError(httpStatus, body) };
	}

	if (typeof body !== 'object' || body === null) {
		return unexpected;
	}
	const page = body as Record<string, unknown>;
	if (
		!Array.isArray(page.items) ||
		!(page.next_cursor === null || typeof page.next_cursor === 'string')
	) {
		return unexpected;
	}

	const campaigns: Campaign[] = [];
	for (const entry of page.items) {
		if (!isCampaignBody(entry)) {
			return unexpected;
		}
		campaigns.push({
			id: entry.id,
			name: entry.name,
			status: entry.status,
			promotionPosture: entry.promotion_posture,
			productContext: entry.product_context,
			icp: entry.icp,
			keywords: entry.keywords,
			subreddits: entry.subreddits,
			competitors: entry.competitors,
			approvedClaims: entry.approved_claims,
			prohibitedClaims: entry.prohibited_claims,
			createdAt: entry.created_at,
			updatedAt: entry.updated_at,
			archivedAt: entry.archived_at
		});
	}

	return {
		apiReachable: true,
		campaigns,
		nextCursor: page.next_cursor,
		detail: null
	};
}

function isCampaignBody(value: unknown): value is ValidatedCampaignBody {
	if (typeof value !== 'object' || value === null) {
		return false;
	}
	const entry = value as Record<string, unknown>;
	return (
		typeof entry.id === 'string' &&
		typeof entry.workspace_id === 'string' &&
		typeof entry.name === 'string' &&
		typeof entry.status === 'string' &&
		isCampaignStatus(entry.status) &&
		typeof entry.promotion_posture === 'string' &&
		isPromotionPosture(entry.promotion_posture) &&
		typeof entry.created_at === 'string' &&
		typeof entry.updated_at === 'string' &&
		(entry.archived_at === null || typeof entry.archived_at === 'string') &&
		(entry.product_context === null || typeof entry.product_context === 'string') &&
		(entry.icp === null || typeof entry.icp === 'string') &&
		LIST_FIELDS.every((field) => isStringList(entry[field]))
	);
}

/** The legal lifecycle transitions per current status; archived is terminal. */
export function nextActions(status: CampaignStatus): LifecycleAction[] {
	switch (status) {
		case 'draft':
			return [{ status: 'active', label: 'Activate' }];
		case 'active':
			return [
				{ status: 'paused', label: 'Pause' },
				{ status: 'archived', label: 'Archive' }
			];
		case 'paused':
			return [
				{ status: 'active', label: 'Resume' },
				{ status: 'archived', label: 'Archive' }
			];
		case 'archived':
			return [];
	}
}

/**
 * Split list input one value per line. Values may contain commas
 * ("Acme, Inc.", "SOC 2, Type II certified"), so lists never split on commas.
 */
export function parseListLines(value: string): string[] {
	return value
		.split(/\r?\n/)
		.map((item) => item.trim())
		.filter((item) => item.length > 0);
}

/** Translate a backend failure into guidance the operator can act on. */
export function explainCampaignError(httpStatus: number, body: unknown): string {
	const code = (body as { detail?: { code?: string } } | null)?.detail?.code;
	switch (code) {
		case 'campaign_invalid_transition':
			return 'That lifecycle change is not allowed.';
		case 'campaign_archived':
			return 'Archived campaigns are read-only.';
		case 'campaign_not_found':
			return 'Campaign not found.';
		case 'unauthorized':
			return 'The backend rejected the request token.';
		case 'api_token_unconfigured':
			return 'The backend has no API token configured.';
		case 'workspace_unconfigured':
			return 'The backend database needs its migrations run.';
		case 'workspace_forbidden':
			return 'The backend token cannot access this workspace.';
		case 'page_cursor_invalid':
			return 'That campaign page link is invalid; return to the newest campaigns.';
		case 'idempotency_key_required':
			return 'The form lost its submission key; refresh and try again.';
		case 'idempotency_key_too_long':
			return 'The form submission key is invalid; refresh and try again.';
		case 'idempotency_key_conflict':
			return 'This submission key was already used for different content.';
		case 'idempotency_key_reconciliation_required':
			return 'This older submission needs operator reconciliation before retrying.';
	}
	if (httpStatus === 422) {
		return 'Some fields were invalid.';
	}
	return `Unexpected error (HTTP ${httpStatus}).`;
}
