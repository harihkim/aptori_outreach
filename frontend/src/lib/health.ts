export type HealthState = {
	/** The backend answered our request, whatever it said. */
	apiReachable: boolean;
	database: 'ok' | 'unavailable' | 'unknown';
	degraded: boolean;
	apiBaseUrl: string;
	detail: string | null;
};

export type HealthBody = {
	status?: string;
	api?: string;
	database?: string;
	detail?: string | null;
};

/**
 * Derive the UI health state from one backend response.
 *
 * `httpStatus` is null when the request never completed (network error or
 * timeout); `body` is null when the response was not valid JSON.
 */
export function parseHealthContract({
	httpStatus,
	body,
	apiBaseUrl
}: {
	httpStatus: number | null;
	body: HealthBody | null;
	apiBaseUrl: string;
}): HealthState {
	const apiReachable = httpStatus !== null;
	// Operational requires the complete healthy contract — HTTP 200 with
	// status "ok", api "reachable", and database "ok". Anything else is
	// degraded, even if individual fields claim otherwise.
	const healthy =
		httpStatus === 200 &&
		body?.status === 'ok' &&
		body?.api === 'reachable' &&
		body?.database === 'ok';
	const database = healthy
		? 'ok'
		: apiReachable && body?.database === 'unavailable'
			? 'unavailable'
			: 'unknown';
	const degraded = !healthy;

	return {
		apiReachable,
		database,
		degraded,
		apiBaseUrl,
		detail: degraded
			? (body?.detail ??
				(apiReachable
					? `Unexpected response (HTTP ${httpStatus})`
					: 'Backend did not answer'))
			: null
	};
}
