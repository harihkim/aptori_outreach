import { isRecord, type DiscoveryRun } from './discovery-contract';

const usdFormatter = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD'
});

const integerFormatter = new Intl.NumberFormat('en-US');

/** Whether the backend priced this run (`reported`) or explicitly did not (`unpriced`). */
export type CostStatus = 'unpriced' | 'reported';

/**
 * Normalize the run's pricing state. This is the single source of truth for
 * the priced/unpriced decision: only a literal `reported` cost_status reads
 * as `reported`. Everything else — `unpriced`, absent, null, or an unknown
 * status word — reads as `unpriced`, never as zero, so a price we do not
 * understand can never masquerade as a free one.
 */
export function costStatusOf(run: DiscoveryRun): CostStatus {
	return run.metrics?.['cost_status'] === 'reported' ? 'reported' : 'unpriced';
}

/**
 * Renders the single-source pricing decision: only runs classified
 * `reported` by costStatusOf may show a dollar figure, and even then only
 * when cost_usd is a finite number. Everything else (null, missing,
 * non-numeric, or a non-reported status such as unknown) says "Not priced"
 * rather than inventing or zeroing a number.
 */
export function costLabel(run: DiscoveryRun): string {
	if (costStatusOf(run) === 'reported') {
		const cost = run.metrics?.['cost_usd'];
		if (typeof cost === 'number' && Number.isFinite(cost)) {
			return usdFormatter.format(cost);
		}
	}
	return 'Not priced';
}

function metricNumber(source: Record<string, unknown>, key: string): number | null {
	const value = source[key];
	return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Measured retrieval usage units in one compact line ("37 requests · 1.2 MB").
 * Counters arrive nested at metrics.usage; a null or absent unit was NOT
 * measured and is omitted rather than shown as zero; when nothing was measured
 * this returns null so callers can leave the line out entirely. The retired
 * top-level metric names were never emitted by the backend and stay ignored.
 */
export function usageLabel(run: DiscoveryRun): string | null {
	const usage = run.metrics?.['usage'];
	if (!isRecord(usage)) {
		return null;
	}
	const parts: string[] = [];
	const requestCount = metricNumber(usage, 'request_count');
	if (requestCount !== null) {
		parts.push(`${integerFormatter.format(requestCount)} requests`);
	}
	const bytes = metricNumber(usage, 'bytes_transferred');
	if (bytes !== null) {
		parts.push(byteSize(bytes));
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
