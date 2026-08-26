import { parseHealthContract, type HealthBody } from '$lib/health';
import { getApiBaseUrl } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, depends }) => {
	depends('app:health');
	const apiBaseUrl = getApiBaseUrl();

	let httpStatus: number | null = null;
	let body: HealthBody | null = null;

	try {
		const response = await fetch(`${apiBaseUrl}/health`, { signal: AbortSignal.timeout(3000) });
		httpStatus = response.status;
		body = await response.json().catch(() => null);
	} catch {
		httpStatus = null;
	}

	return { health: parseHealthContract({ httpStatus, body, apiBaseUrl }) };
};
