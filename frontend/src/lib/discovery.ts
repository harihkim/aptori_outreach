import {
	isFailureClass,
	isObservationStatus,
	isRecord,
	isRunStatus,
	isStringList,
	isTimestampOrNull,
	type DiscoveryRun,
	type Evidence,
	type EvidenceBody,
	type MethodPlanBody,
	type Observation,
	type ObservationsState,
	type PlanQueryBody,
	type RunState,
	type ValidatedObservationBody,
	type ValidatedRunBody
} from './discovery-contract';

import { explainDiscoveryError } from './discovery-errors';

// Public surface: route imports keep working through these re-exports.
export * from './discovery-contract';
export { explainDiscoveryError };
export {
	costLabel,
	costStatusOf,
	latencyLabel,
	usageLabel,
	type CostStatus
} from './discovery-format';
export {
	observationTone,
	runStatusTone,
	type Tone
} from './discovery-tones';

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

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
	const actual = Object.keys(value).sort();
	const expected = [...keys].sort();
	return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function isEvidenceBody(value: unknown): value is EvidenceBody {
	if (!isRecord(value) || typeof value.state !== 'string') {
		return false;
	}
	if (value.state === 'legacy' || value.state === 'none') {
		return hasExactKeys(value, ['state']);
	}
	return (
		value.state === 'bundle' &&
		hasExactKeys(value, ['state', 'bundle_id', 'bundle_sha256', 'artifact_count']) &&
		typeof value.bundle_id === 'string' &&
		typeof value.bundle_sha256 === 'string' &&
		/^[0-9a-f]{64}$/.test(value.bundle_sha256) &&
		typeof value.artifact_count === 'number' &&
		Number.isInteger(value.artifact_count) &&
		value.artifact_count >= 1
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
		(value.failure_class === null ||
			(typeof value.failure_class === 'string' && isFailureClass(value.failure_class))) &&
		(value.failure_reason === null || typeof value.failure_reason === 'string') &&
		typeof value.provider_variant === 'string' &&
		typeof value.config_sha256 === 'string' &&
		typeof value.schema_version === 'number' &&
		typeof value.candidate_count === 'number' &&
		Array.isArray(value.candidates) &&
		(value.normalized_sha256 === null || typeof value.normalized_sha256 === 'string') &&
		(value.elapsed_ms === null || typeof value.elapsed_ms === 'number') &&
		isEvidenceBody(value.evidence) &&
		typeof value.correlation_id === 'string' &&
		isTimestampOrNull(value.started_at) &&
		isTimestampOrNull(value.completed_at) &&
		typeof value.created_at === 'string'
	);
}

function toEvidence(evidence: EvidenceBody): Evidence {
	if (evidence.state !== 'bundle') {
		return evidence;
	}
	return {
		state: 'bundle',
		bundleId: evidence.bundle_id,
		bundleSha256: evidence.bundle_sha256,
		artifactCount: evidence.artifact_count
	};
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
		evidence: toEvidence(entry.evidence),
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
 * the complete contract arrives with known-good status values. Metrics pass
 * through verbatim; cost and usage are read defensively by the formatters.
 */
export function parseDiscoveryRunResponse({
	httpStatus,
	body
}: {
	httpStatus: number | null;
	body: unknown;
}): RunState {
	if (httpStatus === null || httpStatus === 0) {
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
	if (httpStatus === null || httpStatus === 0) {
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

/** Submission id for the start-discovery action of one campaign. */
export function discoverySubmissionId(campaignId: string): string {
	return `discovery:${campaignId}`;
}
