import type { DiscoveryRun } from './discovery-contract';

const usdFormatter = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD'
});

const integerFormatter = new Intl.NumberFormat('en-US');

/** Whether the backend priced this run (`reported`) or explicitly did not (`unpriced`). */
export type CostStatus = 'unpriced' | 'reported';

/**
 * Normalize the run's pricing state.
 *
 * Payloads that carry no cost_status at all are legacy; they read as
 * `unpriced` — never as zero — so an absent price can never masquerade as a
 * free one, and an unknown status word is treated the same honest way.
 */
export function costStatusOf(run: DiscoveryRun): CostStatus {
	return run.metrics?.['cost_status'] === 'reported' ? 'reported' : 'unpriced';
}

/**
 * Cost is honest-or-absent: a numeric cost renders as USD unless the backend
 * explicitly said `unpriced`; anything else (null, missing, non-numeric) says
 * "Not priced" rather than inventing or zeroing a number. Legacy payloads
 * without any cost_status keep rendering their numeric cost exactly as before.
 */
export function costLabel(run: DiscoveryRun): string {
	if (run.metrics !== null) {
		const cost = run.metrics['cost_usd'];
		const status = run.metrics['cost_status'];
		if (
			typeof cost === 'number' &&
			Number.isFinite(cost) &&
			status !== 'unpriced'
		) {
			return usdFormatter.format(cost);
		}
	}
	return 'Not priced';
}

function metricNumber(run: DiscoveryRun, key: string): number | null {
	const value = run.metrics?.[key];
	return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Measured retrieval usage units in one compact line ("Browser 12,340 ms ·
 * 1.2 MB · 37 requests"). A null or absent unit was NOT measured and is
 * omitted rather than shown as zero; when nothing was measured this returns
 * null so callers can leave the line out entirely.
 */
export function usageLabel(run: DiscoveryRun): string | null {
	const parts: string[] = [];
	const wallMs = metricNumber(run, 'browser_wall_time_ms');
	if (wallMs !== null) {
		parts.push(`Browser ${integerFormatter.format(wallMs)} ms`);
	}
	const bytes = metricNumber(run, 'bytes_transferred');
	if (bytes !== null) {
		parts.push(byteSize(bytes));
	}
	const requestCount = metricNumber(run, 'network_request_count');
	if (requestCount !== null) {
		parts.push(`${integerFormatter.format(requestCount)} requests`);
	}
	return parts.length > 0 ? parts.join(' · ') : null;
}

function byteSize(bytes: number): string {
	if (bytes < 1024) {
		return `${integerFormatter.format(bytes)} B`;
	}
	const kib = bytes / 1024;
	if (kib < 1024) {
		return `${kib.toFixed(1)} KB`;
	}
	const mib = kib / 1024;
	if (mib < 1024) {
		return `${mib.toFixed(1)} MB`;
	}
	return `${(mib / 1024).toFixed(1)} GB`;
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
