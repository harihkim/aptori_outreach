export const RUN_STATUSES = [
	'queued',
	'running',
	'succeeded',
	'partial',
	'failed',
	'cancelled'
] as const;
export const OBSERVATION_STATUSES = [
	'success',
	'no_results',
	'incomplete',
	'blocked',
	'rate_limited',
	'auth_required',
	'forbidden',
	'upstream_unavailable',
	'parse_failed',
	'transport_failed',
	'runtime_verification_failed',
	'failed'
] as const;
/** Observation outcomes that still carry usable evidence. */
export const USABLE_STATUSES = ['success', 'no_results', 'incomplete'] as const;

export type RunStatus = (typeof RUN_STATUSES)[number];
export type ObservationStatus = (typeof OBSERVATION_STATUSES)[number];

export type PlanQueryBody = {
	id: string;
	pattern: string | null;
	query: string;
	subreddits: string[];
};

export type MethodPlanBody = {
	source: string;
	provider_variant: string;
	config_sha256: string;
	document_sha256: string;
	queries: PlanQueryBody[];
};

/** The run exactly as the backend sends it (snake_case wire shape). */
export type DiscoveryRunBody = {
	id: string;
	campaign_id: string;
	workspace_id: string;
	status: string;
	method_plan: MethodPlanBody;
	correlation_id: string;
	metrics: Record<string, unknown> | null;
	started_at: string | null;
	completed_at: string | null;
	created_at: string;
	updated_at: string;
};

/** The validated wire shape: status is a known-good run status. */
type ValidatedRunBody = Omit<DiscoveryRunBody, 'status'> & { status: RunStatus };

export type DiscoveryPlanQuery = {
	id: string;
	pattern: string | null;
	query: string;
	subreddits: string[];
};

export type DiscoveryMethodPlanView = {
	source: string;
	providerVariant: string;
	configSha256: string;
	documentSha256: string;
	queries: DiscoveryPlanQuery[];
};

export type DiscoveryRun = {
	id: string;
	campaignId: string;
	workspaceId: string;
	status: RunStatus;
	methodPlan: DiscoveryMethodPlanView;
	correlationId: string;
	metrics: Record<string, unknown> | null;
	startedAt: string | null;
	completedAt: string | null;
	createdAt: string;
	updatedAt: string;
};

export type ObservationBody = {
	id: string;
	query_id: string;
	capability: string;
	status: string;
	failure_class: string | null;
	failure_reason: string | null;
	provider_variant: string;
	config_sha256: string;
	schema_version: number;
	candidate_count: number;
	candidates: unknown[];
	normalized_sha256: string | null;
	elapsed_ms: number | null;
	evidence_directory: string;
	correlation_id: string;
	started_at: string | null;
	completed_at: string | null;
	created_at: string;
};

type ValidatedObservationBody = Omit<ObservationBody, 'status'> & {
	status: ObservationStatus;
};

export type Observation = {
	id: string;
	queryId: string;
	capability: string;
	status: ObservationStatus;
	failureClass: string | null;
	failureReason: string | null;
	providerVariant: string;
	configSha256: string;
	schemaVersion: number;
	candidateCount: number;
	candidates: unknown[];
	normalizedSha256: string | null;
	elapsedMs: number | null;
	evidenceDirectory: string;
	correlationId: string;
	startedAt: string | null;
	completedAt: string | null;
	createdAt: string;
};

export type RunState = {
	/** The backend answered our request, whatever it said. */
	apiReachable: boolean;
	run: DiscoveryRun | null;
	detail: string | null;
};

export type ObservationsState = {
	apiReachable: boolean;
	items: Observation[];
	nextCursor: string | null;
	detail: string | null;
};

function isRunStatus(value: string): value is RunStatus {
	return (RUN_STATUSES as readonly string[]).includes(value);
}

function isObservationStatus(value: string): value is ObservationStatus {
	return (OBSERVATION_STATUSES as readonly string[]).includes(value);
}

function isStringList(value: unknown): value is string[] {
	return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isPlanQuery(value: unknown): value is PlanQueryBody {
	if (!isRecord(value)) {
		return false;
	}
	return (
		typeof value.id === 'string' &&
		value.id.length > 0 &&
		(value.pattern === null || typeof value.pattern === 'string') &&
		typeof value.query === 'string' &&
		value.query.length > 0 &&
		isStringList(value.subreddits)
	);
}

function isMethodPlan(value: unknown): value is MethodPlanBody {
	if (!isRecord(value)) {
		return false;
	}
	return (
		typeof value.source === 'string' &&
		typeof value.provider_variant === 'string' &&
		typeof value.config_sha256 === 'string' &&
		typeof value.document_sha256 === 'string' &&
		Array.isArray(value.queries) &&
		value.queries.every(isPlanQuery)
	);
}

function isTimestampOrNull(value: unknown): value is string | null {
	return value === null || typeof value === 'string';
}

function isRunBody(value: unknown): value is ValidatedRunBody {
	if (!isRecord(value)) {
		return false;
	}
	return (
		typeof value.id === 'string' &&
		typeof value.campaign_id === 'string' &&
		typeof value.workspace_id === 'string' &&
		typeof value.status === 'string' &&
		isRunStatus(value.status) &&
		isMethodPlan(value.method_plan) &&
		typeof value.correlation_id === 'string' &&
		(value.metrics === null || isRecord(value.metrics)) &&
		isTimestampOrNull(value.started_at) &&
		isTimestampOrNull(value.completed_at) &&
		typeof value.created_at === 'string' &&
		typeof value.updated_at === 'string'
	);
}

function isObservationBody(value: unknown): value is ValidatedObservationBody {
	if (!isRecord(value)) {
		return false;
	}
	return (
		typeof value.id === 'string' &&
		typeof value.query_id === 'string' &&
		typeof value.capability === 'string' &&
		typeof value.status === 'string' &&
		isObservationStatus(value.status) &&
		(value.failure_class === null || typeof value.failure_class === 'string') &&
		(value.failure_reason === null || typeof value.failure_reason === 'string') &&
		typeof value.provider_variant === 'string' &&
		typeof value.config_sha256 === 'string' &&
		typeof value.schema_version === 'number' &&
		typeof value.candidate_count === 'number' &&
		Array.isArray(value.candidates) &&
		(value.normalized_sha256 === null || typeof value.normalized_sha256 === 'string') &&
		(value.elapsed_ms === null || typeof value.elapsed_ms === 'number') &&
		typeof value.evidence_directory === 'string' &&
		typeof value.correlation_id === 'string' &&
		isTimestampOrNull(value.started_at) &&
		isTimestampOrNull(value.completed_at) &&
		typeof value.created_at === 'string'
	);
}

function toRun(entry: ValidatedRunBody): DiscoveryRun {
	return {
		id: entry.id,
		campaignId: entry.campaign_id,
		workspaceId: entry.workspace_id,
		status: entry.status,
		methodPlan: {
			source: entry.method_plan.source,
			providerVariant: entry.method_plan.provider_variant,
			configSha256: entry.method_plan.config_sha256,
			documentSha256: entry.method_plan.document_sha256,
			queries: entry.method_plan.queries.map((query) => ({
				id: query.id,
				pattern: query.pattern,
				query: query.query,
				subreddits: query.subreddits
			}))
		},
		correlationId: entry.correlation_id,
		metrics: entry.metrics,
		startedAt: entry.started_at,
		completedAt: entry.completed_at,
		createdAt: entry.created_at,
		updatedAt: entry.updated_at
	};
}

function toObservation(entry: ValidatedObservationBody): Observation {
	return {
		id: entry.id,
		queryId: entry.query_id,
		capability: entry.capability,
		status: entry.status,
		failureClass: entry.failure_class,
		failureReason: entry.failure_reason,
		providerVariant: entry.provider_variant,
		configSha256: entry.config_sha256,
		schemaVersion: entry.schema_version,
		candidateCount: entry.candidate_count,
		candidates: entry.candidates,
		normalizedSha256: entry.normalized_sha256,
		elapsedMs: entry.elapsed_ms,
		evidenceDirectory: entry.evidence_directory,
		correlationId: entry.correlation_id,
		startedAt: entry.started_at,
		completedAt: entry.completed_at,
		createdAt: entry.created_at
	};
}

/**
 * Derive the run state from one backend response.
 *
 * `httpStatus` is null when the request never completed; `body` is unknown
 * because the backend may answer with anything. The run is trusted only when
 * the complete contract arrives with known-good status values.
 */
export function parseDiscoveryRunResponse({
	httpStatus,
	body
}: {
	httpStatus: number | null;
	body: unknown;
}): RunState {
	if (httpStatus === null) {
		return { apiReachable: false, run: null, detail: 'Backend did not answer' };
	}

	const unexpected: RunState = {
		apiReachable: true,
		run: null,
		detail: `Unexpected response (HTTP ${httpStatus})`
	};

	if (httpStatus !== 200) {
		return { ...unexpected, detail: explainDiscoveryError(httpStatus, body) };
	}

	if (!isRunBody(body)) {
		return unexpected;
	}

	return { apiReachable: true, run: toRun(body), detail: null };
}

/** Derive the observations page state from one backend response. */
export function parseObservationsResponse({
	httpStatus,
	body
}: {
	httpStatus: number | null;
	body: unknown;
}): ObservationsState {
	if (httpStatus === null) {
		return {
			apiReachable: false,
			items: [],
			nextCursor: null,
			detail: 'Backend did not answer'
		};
	}

	const unexpected: ObservationsState = {
		apiReachable: true,
		items: [],
		nextCursor: null,
		detail: `Unexpected response (HTTP ${httpStatus})`
	};

	if (httpStatus !== 200) {
		return { ...unexpected, detail: explainDiscoveryError(httpStatus, body) };
	}

	if (!isRecord(body) || !Array.isArray(body.items)) {
		return unexpected;
	}
	const nextCursor = body.next_cursor;
	if (!(nextCursor === null || typeof nextCursor === 'string')) {
		return unexpected;
	}

	const items: Observation[] = [];
	for (const entry of body.items) {
		if (!isObservationBody(entry)) {
			return unexpected;
		}
		items.push(toObservation(entry));
	}

	return { apiReachable: true, items, nextCursor, detail: null };
}

/** Translate a discovery backend failure into guidance the operator can act on. */
export function explainDiscoveryError(httpStatus: number, body: unknown): string {
	const code = (body as { detail?: { code?: string } } | null)?.detail?.code;
	switch (code) {
		case 'campaign_not_active':
			return 'Only ACTIVE campaigns can run discovery.';
		case 'campaign_not_found':
			return 'Campaign not found.';
		case 'discovery_run_not_found':
			return 'Discovery run not found.';
		case 'worker_queue_unavailable':
			return 'The worker queue is unavailable; retrying the same request will safely re-enqueue.';
		case 'retrieval_inputs_unavailable':
			return 'Retrieval inputs are misconfigured on the backend.';
		case 'unauthorized':
			return 'The backend rejected the request token.';
		case 'api_token_unconfigured':
			return 'The backend has no API token configured.';
		case 'workspace_unconfigured':
			return 'The backend database needs its migrations run.';
		case 'workspace_forbidden':
			return 'The backend token cannot access this workspace.';
		case 'page_cursor_invalid':
			return 'That page link is invalid; return to the newest data.';
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

const usdFormatter = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD'
});

/**
 * Cost is honest-or-absent: the backend only reports it when it knows, and
 * the screen says "not reported" rather than inventing a number.
 */
export function costLabel(run: DiscoveryRun): string {
	const cost = run.metrics?.['cost_usd'];
	if (run.metrics !== null && typeof cost === 'number') {
		return usdFormatter.format(cost);
	}
	return 'not reported';
}

/** Humanized elapsed time; an em dash when nothing was measured. */
export function latencyLabel(ms: number | null): string {
	if (ms === null) {
		return '—';
	}
	if (ms < 1000) {
		return `${ms} ms`;
	}
	if (ms < 60_000) {
		return `${(ms / 1000).toFixed(1)} s`;
	}
	const minutes = Math.floor(ms / 60_000);
	const seconds = Math.round((ms % 60_000) / 1000);
	return `${minutes}m ${seconds}s`;
}

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

/** Badge tone per run status for consistent coloring across screens. */
export function runStatusTone(status: RunStatus): Tone {
	switch (status) {
		case 'queued':
			return 'neutral';
		case 'running':
			return 'info';
		case 'succeeded':
			return 'success';
		case 'partial':
			return 'warning';
		case 'failed':
		case 'cancelled':
			return 'danger';
	}
}

/** Badge tone per observation status: usable evidence is never danger. */
export function observationTone(status: ObservationStatus): Tone {
	if (status === 'success') {
		return 'success';
	}
	if (status === 'no_results' || status === 'incomplete') {
		return 'warning';
	}
	return 'danger';
}

/** Submission id for the start-discovery action of one campaign. */
export function discoverySubmissionId(campaignId: string): string {
	return `discovery:${campaignId}`;
}
