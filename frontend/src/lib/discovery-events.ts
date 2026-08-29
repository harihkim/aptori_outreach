import { isRecord } from './discovery-contract';

/**
 * Event families defined by the REST/SSE contract. The first four are the
 * discovery progress slice; later families share the same envelope so the
 * page can safely ignore them until their UI exists.
 */
export const DISCOVERY_EVENT_TYPES = [
	'discovery.started',
	'discovery.candidate_found',
	'retrieval.observed',
	'discovery.completed',
	'conversation.normalized',
	'analysis.completed',
	'draft.version_created',
	'approval.created',
	'approval.revoked',
	'approval.expired',
	'approval.consumed',
	'media.started',
	'media.completed',
	'browser.started',
	'browser.ready_for_human',
	'job.failed'
] as const;

export type DiscoveryEventType = (typeof DISCOVERY_EVENT_TYPES)[number];

export type DiscoveryProgressEvent = {
	type: DiscoveryEventType;
	id: string;
	runId: string;
	workspaceId: string;
	correlationId: string;
	occurredAt: string;
	payload: Record<string, unknown>;
};

function isEventType(value: string): value is DiscoveryEventType {
	return (DISCOVERY_EVENT_TYPES as readonly string[]).includes(value);
}

function requiredString(value: unknown): value is string {
	return typeof value === 'string' && value.length > 0;
}

/**
 * Parse one EventSource message without performing side effects.
 *
 * The SSE event name and the JSON envelope's type are both checked. This
 * prevents a malformed or misrouted message from driving a run refresh, and
 * keeps all wire-shape knowledge in a pure, easily tested module.
 */
export function parseDiscoveryEvent(
	eventType: string,
	data: string
): DiscoveryProgressEvent | null {
	if (!isEventType(eventType)) {
		return null;
	}

	let value: unknown;
	try {
		value = JSON.parse(data);
	} catch {
		return null;
	}
	if (!isRecord(value) || value.type !== eventType) {
		return null;
	}
	if (
		!requiredString(value.id) ||
		!requiredString(value.run_id) ||
		!requiredString(value.workspace_id) ||
		!requiredString(value.correlation_id) ||
		!requiredString(value.occurred_at) ||
		!isRecord(value.payload)
	) {
		return null;
	}

	return {
		type: eventType,
		id: value.id,
		runId: value.run_id,
		workspaceId: value.workspace_id,
		correlationId: value.correlation_id,
		occurredAt: value.occurred_at,
		payload: value.payload
	};
}
