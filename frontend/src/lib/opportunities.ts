import { isRecord } from './discovery-contract';
import { explainDiscoveryError } from './discovery-errors';

export const OPPORTUNITY_STATUSES = ['open', 'saved', 'dismissed', 'acted_on'] as const;
export const RECOMMENDED_ACTIONS = [
	'ignore',
	'monitor',
	'reply_helpfully',
	'reply_with_product',
	'content_opportunity'
] as const;
/** Scored factors in formula order, then the deliberately unscored one. */
export const FACTOR_ORDER = [
	'relevance',
	'pain_intensity',
	'buying_intent',
	'replyability',
	'product_fit',
	'promotion_fit'
] as const;

export type OpportunityStatus = (typeof OPPORTUNITY_STATUSES)[number];
export type RecommendedAction = (typeof RECOMMENDED_ACTIONS)[number];
export type FactorName = (typeof FACTOR_ORDER)[number];

export type AnalysisFactors = Record<FactorName, number> & { confidence: number };

export type Opportunity = {
	id: string;
	campaignId: string;
	conversationId: string;
	opportunityScore: number;
	formulaVersion: string;
	status: OpportunityStatus;
	postCreatedAt: string;
	scoredAt: string;
	conversation: {
		id: string;
		externalId: string;
		title: string;
		subreddit: string | null;
		url: string | null;
		postScore: number | null;
		reportedCommentCount: number | null;
	};
	analysis: {
		id: string;
		factors: AnalysisFactors;
		topic: string;
		persona: string | null;
		recommendedAction: RecommendedAction;
		rationale: string;
	};
	modelRun: {
		taskId: string;
		taskVersion: string;
		promptVersion: string;
		schemaVersion: string;
		servedTier: string;
		requestedModel: string | null;
		actualModel: string | null;
		endpointLabel: string | null;
		inputTokens: number | null;
		outputTokens: number | null;
		requestCount: number;
	};
};

export type OpportunitiesState = {
	/** The backend answered our request, whatever it said. */
	apiReachable: boolean;
	items: Opportunity[];
	detail: string | null;
};

const ACTION_LABELS: Record<RecommendedAction, string> = {
	ignore: 'Ignore',
	monitor: 'Monitor',
	reply_helpfully: 'Reply helpfully',
	reply_with_product: 'Reply with product',
	content_opportunity: 'Content opportunity'
};

const FACTOR_LABELS: Record<FactorName, string> = {
	relevance: 'Relevance',
	pain_intensity: 'Pain intensity',
	buying_intent: 'Buying intent',
	replyability: 'Replyability',
	product_fit: 'Product fit',
	promotion_fit: 'Promotion fit'
};

const STATUS_LABELS: Record<OpportunityStatus, string> = {
	open: 'Open',
	saved: 'Saved',
	dismissed: 'Dismissed',
	acted_on: 'Acted on'
};

export function actionLabel(action: RecommendedAction): string {
	return ACTION_LABELS[action];
}

export function factorLabel(factor: FactorName): string {
	return FACTOR_LABELS[factor];
}

export function statusLabel(status: OpportunityStatus): string {
	return STATUS_LABELS[status];
}

/** Two decimals of a unit-interval score; never a percentage, never rounded to 1.00 by accident. */
export function scoreLabel(score: number): string {
	return (Math.floor(score * 100) / 100).toFixed(2);
}

/** Whole-unit age of the source post relative to `now`; the decay input, not a timestamp. */
export function ageLabel(postCreatedAt: string, now: Date): string {
	const created = Date.parse(postCreatedAt);
	if (!Number.isFinite(created)) {
		return 'age unknown';
	}
	const hours = Math.max(0, (now.getTime() - created) / 3_600_000);
	if (hours < 1) {
		return 'under an hour old';
	}
	if (hours < 48) {
		return `${Math.floor(hours)}h old`;
	}
	return `${Math.floor(hours / 24)}d old`;
}

export function explainOpportunityError(httpStatus: number, body: unknown): string {
	const code = (body as { detail?: { code?: string } } | null)?.detail?.code;
	if (code === 'opportunity_not_found') {
		return 'Opportunity not found.';
	}
	return explainDiscoveryError(httpStatus, body);
}

function isUnitInterval(value: unknown): value is number {
	return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isNullableString(value: unknown): value is string | null {
	return value === null || typeof value === 'string';
}

function isNullableNumber(value: unknown): value is number | null {
	return value === null || (typeof value === 'number' && Number.isFinite(value));
}

function isStatus(value: unknown): value is OpportunityStatus {
	return typeof value === 'string' && (OPPORTUNITY_STATUSES as readonly string[]).includes(value);
}

function isAction(value: unknown): value is RecommendedAction {
	return typeof value === 'string' && (RECOMMENDED_ACTIONS as readonly string[]).includes(value);
}

function parseFactors(value: unknown): AnalysisFactors | null {
	if (!isRecord(value) || !isUnitInterval(value.confidence)) {
		return null;
	}
	const factors: Partial<AnalysisFactors> = { confidence: value.confidence };
	for (const name of FACTOR_ORDER) {
		const factor = value[name];
		if (!isUnitInterval(factor)) {
			return null;
		}
		factors[name] = factor;
	}
	return factors as AnalysisFactors;
}

function parseOpportunity(raw: unknown): Opportunity | null {
	if (
		!isRecord(raw) ||
		typeof raw.id !== 'string' ||
		typeof raw.campaign_id !== 'string' ||
		typeof raw.conversation_id !== 'string' ||
		!isUnitInterval(raw.opportunity_score) ||
		typeof raw.formula_version !== 'string' ||
		!isStatus(raw.status) ||
		typeof raw.post_created_at !== 'string' ||
		typeof raw.scored_at !== 'string' ||
		!isRecord(raw.conversation) ||
		!isRecord(raw.analysis) ||
		!isRecord(raw.model_run)
	) {
		return null;
	}
	const conversation = raw.conversation;
	const analysis = raw.analysis;
	const modelRun = raw.model_run;
	const factors = parseFactors(analysis.factors);
	if (
		factors === null ||
		typeof conversation.id !== 'string' ||
		typeof conversation.canonical_external_discussion_id !== 'string' ||
		typeof conversation.title !== 'string' ||
		!isNullableString(conversation.subreddit) ||
		!isNullableString(conversation.url) ||
		!isNullableNumber(conversation.post_score) ||
		!isNullableNumber(conversation.reported_comment_count) ||
		typeof analysis.id !== 'string' ||
		typeof analysis.topic !== 'string' ||
		!isNullableString(analysis.persona) ||
		!isAction(analysis.recommended_action) ||
		typeof analysis.rationale !== 'string' ||
		typeof modelRun.task_id !== 'string' ||
		typeof modelRun.task_version !== 'string' ||
		typeof modelRun.prompt_version !== 'string' ||
		typeof modelRun.schema_version !== 'string' ||
		typeof modelRun.served_tier !== 'string' ||
		!isNullableString(modelRun.requested_model) ||
		!isNullableString(modelRun.actual_model) ||
		!isNullableString(modelRun.endpoint_label) ||
		!isNullableNumber(modelRun.input_tokens) ||
		!isNullableNumber(modelRun.output_tokens) ||
		typeof modelRun.request_count !== 'number'
	) {
		return null;
	}
	return {
		id: raw.id,
		campaignId: raw.campaign_id,
		conversationId: raw.conversation_id,
		opportunityScore: raw.opportunity_score,
		formulaVersion: raw.formula_version,
		status: raw.status,
		postCreatedAt: raw.post_created_at,
		scoredAt: raw.scored_at,
		conversation: {
			id: conversation.id,
			externalId: conversation.canonical_external_discussion_id,
			title: conversation.title,
			subreddit: conversation.subreddit,
			url: conversation.url,
			postScore: conversation.post_score,
			reportedCommentCount: conversation.reported_comment_count
		},
		analysis: {
			id: analysis.id,
			factors,
			topic: analysis.topic,
			persona: analysis.persona,
			recommendedAction: analysis.recommended_action,
			rationale: analysis.rationale
		},
		modelRun: {
			taskId: modelRun.task_id,
			taskVersion: modelRun.task_version,
			promptVersion: modelRun.prompt_version,
			schemaVersion: modelRun.schema_version,
			servedTier: modelRun.served_tier,
			requestedModel: modelRun.requested_model,
			actualModel: modelRun.actual_model,
			endpointLabel: modelRun.endpoint_label,
			inputTokens: modelRun.input_tokens,
			outputTokens: modelRun.output_tokens,
			requestCount: modelRun.request_count
		}
	};
}

/**
 * Derive the Inbox state from one backend response. The listing is trusted
 * only when every entry carries the complete, range-valid contract; one
 * malformed row rejects the page rather than rendering a partial ranking.
 */
export function parseOpportunitiesResponse({
	httpStatus,
	body
}: {
	httpStatus: number | null;
	body: unknown;
}): OpportunitiesState {
	if (httpStatus === null || httpStatus === 0) {
		return { apiReachable: false, items: [], detail: 'Backend did not answer' };
	}
	const unexpected: OpportunitiesState = {
		apiReachable: true,
		items: [],
		detail: `Unexpected response (HTTP ${httpStatus})`
	};
	if (httpStatus !== 200) {
		return { ...unexpected, detail: explainOpportunityError(httpStatus, body) };
	}
	if (!isRecord(body) || !Array.isArray(body.items)) {
		return unexpected;
	}
	const items: Opportunity[] = [];
	for (const raw of body.items) {
		const parsed = parseOpportunity(raw);
		if (parsed === null) {
			return unexpected;
		}
		items.push(parsed);
	}
	return { apiReachable: true, items, detail: null };
}
