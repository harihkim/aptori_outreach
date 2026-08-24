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
export type ValidatedRunBody = Omit<DiscoveryRunBody, 'status'> & { status: RunStatus };

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

export type ValidatedObservationBody = Omit<ObservationBody, 'status'> & {
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

export function isRunStatus(value: string): value is RunStatus {
	return (RUN_STATUSES as readonly string[]).includes(value);
}

export function isObservationStatus(value: string): value is ObservationStatus {
	return (OBSERVATION_STATUSES as readonly string[]).includes(value);
}

export function isStringList(value: unknown): value is string[] {
	return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

export function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isTimestampOrNull(value: unknown): value is string | null {
	return value === null || typeof value === 'string';
}
