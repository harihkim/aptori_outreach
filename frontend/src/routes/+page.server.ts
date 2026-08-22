import { env } from '$env/dynamic/public';
import type { PageServerLoad } from './$types';

export type HealthState = {
	ok: boolean;
	apiBaseUrl: string;
	httpStatus: number | null;
	database: string | null;
	detail: string | null;
};

export const load: PageServerLoad = async ({ fetch, depends }) => {
	depends('app:health');
	const apiBaseUrl = env.PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

	let httpStatus: number | null = null;
	let body: { status?: string; database?: string } | null = null;
	let errorMessage: string | null = null;

	try {
		const response = await fetch(`${apiBaseUrl}/health`, { signal: AbortSignal.timeout(3000) });
		httpStatus = response.status;
		body = await response.json().catch(() => null);
	} catch (error) {
		httpStatus = null;
		errorMessage = error instanceof Error ? `${error.message}: ${(error as { cause?: { message?: string } }).cause?.message ?? ''}` : String(error);
	}

	const ok = httpStatus === 200 && body?.status === 'ok' && body?.database === 'ok';
	const state: HealthState = {
		ok,
		apiBaseUrl,
		httpStatus,
		database: body?.database ?? null,
		detail: ok ? null : (errorMessage ?? (body ? `Unexpected response (HTTP ${httpStatus})` : 'Backend unreachable'))
	};
	return { health: state };
};
