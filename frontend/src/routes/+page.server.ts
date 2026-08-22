import { env } from '$env/dynamic/public';
import type { PageServerLoad } from './$types';

export type HealthState = {
	/** The backend answered our request, whatever it said. */
	apiReachable: boolean;
	database: 'ok' | 'unavailable' | 'unknown';
	degraded: boolean;
	apiBaseUrl: string;
	detail: string | null;
};

type HealthBody = {
	status?: string;
	api?: string;
	database?: string;
	detail?: string | null;
};

export const load: PageServerLoad = async ({ fetch, depends }) => {
	depends('app:health');
	const apiBaseUrl = env.PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

	let httpStatus: number | null = null;
	let body: HealthBody | null = null;

	try {
		const response = await fetch(`${apiBaseUrl}/health`, { signal: AbortSignal.timeout(3000) });
		httpStatus = response.status;
		body = await response.json().catch(() => null);
	} catch {
		httpStatus = null;
	}

	const apiReachable = httpStatus !== null;
	const database =
		body?.database === 'ok' || body?.database === 'unavailable' ? body.database : 'unknown';
	const degraded = !apiReachable || database !== 'ok';

	const state: HealthState = {
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
	return { health: state };
};
