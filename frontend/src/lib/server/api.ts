import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

export function getApiBaseUrl(): string {
	return publicEnv.PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
}

export type ApiResult = { ok: boolean; status: number; body: unknown };

export type ApiFetch = (
	input: string | URL | Request,
	init?: RequestInit
) => Promise<Response>;

/**
 * One server-side backend call shared by every page.
 *
 * Unified retry semantics: GET requests retry exactly once, and only on a
 * network-level failure (status 0 — refused, aborted, timed out), because
 * repeating a read can never duplicate work; non-read (write) requests NEVER
 * blind-retry — callers own replay policy through their Idempotency-Key.
 * Everything else matches the behavior both pages already shipped: JSON
 * content type on every request, bearer token from API_TOKEN when configured,
 * Idempotency-Key only on writes, null body for payload-less reads, JSON-
 * stringified body otherwise, and `${apiBaseUrl}${path}` joined verbatim.
 */
export async function callApi(
	requestFetch: ApiFetch,
	method: string,
	path: string,
	payload: unknown,
	{
		write = false,
		timeoutMs = 5000,
		idempotencyKey = crypto.randomUUID()
	}: { write?: boolean; timeoutMs?: number; idempotencyKey?: string } = {}
): Promise<ApiResult> {
	const headers: Record<string, string> = { 'content-type': 'application/json' };
	if (env.API_TOKEN) {
		headers['Authorization'] = `Bearer ${env.API_TOKEN}`;
	}
	if (write) {
		headers['Idempotency-Key'] = idempotencyKey;
	}

	async function attempt(): Promise<ApiResult> {
		try {
			const response = await requestFetch(`${getApiBaseUrl()}${path}`, {
				method,
				headers,
				body: payload === null ? null : JSON.stringify(payload),
				signal: AbortSignal.timeout(timeoutMs)
			});
			const body = await response.json().catch(() => null);
			return { ok: response.ok, status: response.status, body };
		} catch {
			return { ok: false, status: 0, body: null };
		}
	}

	const first = await attempt();
	if (method === 'GET' && !first.ok && first.status === 0) {
		return attempt();
	}
	return first;
}
