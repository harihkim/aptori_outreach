import type { CostStatus } from './discovery-format';
import type { ObservationStatus, RunStatus } from './discovery-contract';

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

/** Badge tone per run status for consistent coloring across screens. */
export function runStatusTone(status: RunStatus): Tone {
	switch (status) {
		case 'queued':
			return 'neutral';
		case 'running':
			return 'info';
		case 'succeeded':
			return 'success';
		case 'partial':
			return 'warning';
		case 'failed':
		case 'cancelled':
			return 'danger';
	}
}

/** Badge tone per observation status: usable evidence is never danger. */
export function observationTone(status: ObservationStatus): Tone {
	if (status === 'success') {
		return 'success';
	}
	if (status === 'no_results' || status === 'incomplete') {
		return 'warning';
	}
	return 'danger';
}

/**
 * Pricing state is informational, never an alarm: unpriced means "the
 * backend did not measure a price", which is neither error nor warning.
 */
export function costStatusTone(status: CostStatus): Tone {
	return 'neutral';
}
