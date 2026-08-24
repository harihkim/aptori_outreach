import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POLL_BASE_MS, POLL_MAX_MS, pollDelayMs, startDiscoveryRunPolling } from './polling';

describe('pollDelayMs', () => {
	it('doubles from the 3s base and clamps at the 15s cap', () => {
		expect(POLL_BASE_MS).toBe(3000);
		expect(POLL_MAX_MS).toBe(15000);
		expect(pollDelayMs(0)).toBe(3000);
		expect(pollDelayMs(1)).toBe(6000);
		expect(pollDelayMs(2)).toBe(12000);
		expect(pollDelayMs(3)).toBe(15000);
		expect(pollDelayMs(4)).toBe(15000);
		expect(pollDelayMs(50)).toBe(15000);
	});
});

describe('startDiscoveryRunPolling', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('fires onPoll along the full backoff ladder while live', async () => {
		const onPoll = vi.fn();
		startDiscoveryRunPolling(() => ({ live: true, reachable: false }), onPoll);

		await vi.advanceTimersByTimeAsync(2999);
		expect(onPoll).toHaveBeenCalledTimes(0);
		await vi.advanceTimersByTimeAsync(1);
		expect(onPoll).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(6000);
		expect(onPoll).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(12000);
		expect(onPoll).toHaveBeenCalledTimes(3);
		await vi.advanceTimersByTimeAsync(15000);
		expect(onPoll).toHaveBeenCalledTimes(4);
		// The cap holds: another 15s yields exactly one more poll.
		await vi.advanceTimersByTimeAsync(14999);
		expect(onPoll).toHaveBeenCalledTimes(4);
		await vi.advanceTimersByTimeAsync(1);
		expect(onPoll).toHaveBeenCalledTimes(5);
	});

	it('stops scheduling entirely once the gate reports a terminal status', async () => {
		let live = true;
		const onPoll = vi.fn();
		startDiscoveryRunPolling(() => ({ live, reachable: false }), onPoll);

		await vi.advanceTimersByTimeAsync(3000);
		expect(onPoll).toHaveBeenCalledTimes(1);

		live = false;
		await vi.advanceTimersByTimeAsync(60_000);
		expect(onPoll).toHaveBeenCalledTimes(1);
	});

	it('never schedules when already terminal at creation', async () => {
		const onPoll = vi.fn();
		startDiscoveryRunPolling(() => ({ live: false, reachable: false }), onPoll);

		await vi.advanceTimersByTimeAsync(60_000);
		expect(onPoll).not.toHaveBeenCalled();
	});

	it('clears the pending timer on stop so nothing fires afterwards', async () => {
		const onPoll = vi.fn();
		const stop = startDiscoveryRunPolling(() => ({ live: true, reachable: false }), onPoll);

		await vi.advanceTimersByTimeAsync(1000);
		stop();
		await vi.advanceTimersByTimeAsync(60_000);

		expect(onPoll).not.toHaveBeenCalled();
	});
});
