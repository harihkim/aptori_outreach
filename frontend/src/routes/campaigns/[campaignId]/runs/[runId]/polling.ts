export const POLL_BASE_MS = 3000;
export const POLL_MAX_MS = 15000;

/**
 * Consecutive failed polls double the delay up to this exponent
 * (3s -> 6s -> 12s); anything beyond stays clamped by POLL_MAX_MS.
 * Successful polls reset the counter so backoff only applies while
 * the backend is unreachable.
 */
const BACKOFF_MAX_EXPONENT = 3;

export interface DiscoveryPollGate {
	/** True while the run status is queued/running, i.e. the outcome can still change. */
	live: boolean;
	/** True while the backend answered the latest request. */
	reachable: boolean;
}

export function pollDelayMs(attempts: number): number {
	return Math.min(POLL_BASE_MS * 2 ** Math.min(attempts, BACKOFF_MAX_EXPONENT), POLL_MAX_MS);
}

/**
 * Self-scheduling poll timer chain for discovery runs.
 *
 * Must be created from a reactive context that re-runs it whenever the
 * gate inputs change (an {@attach} function): every re-run tears down the
 * pending timer and starts a fresh chain whose attempt counter is zero,
 * which is what makes a newly reachable backend reset the backoff.
 * Between re-runs the counter is a plain local variable - no component
 * state is mutated, and the returned stopper clears the pending timer so
 * no poll can fire after unmount or a terminal transition.
 */
export function startDiscoveryRunPolling(
	gate: () => DiscoveryPollGate,
	onPoll: () => void
): () => void {
	// Read once so the calling reaction registers its dependencies; ticks
	// below re-read untracked so they always see the freshest values.
	const initial = gate();
	if (!initial.live) {
		return () => {};
	}

	let attempts = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;

	const stop = () => {
		if (timer !== undefined) {
			clearTimeout(timer);
			timer = undefined;
		}
	};

	const schedule = () => {
		timer = setTimeout(tick, pollDelayMs(attempts));
	};

	const tick = () => {
		timer = undefined;
		const snapshot = gate();
		if (!snapshot.live) {
			return;
		}
		if (snapshot.reachable) {
			attempts = 0;
		} else {
			attempts += 1;
		}
		onPoll();
		schedule();
	};

	schedule();

	return stop;
}
