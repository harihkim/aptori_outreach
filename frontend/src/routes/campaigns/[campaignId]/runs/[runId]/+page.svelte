<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { Badge } from '$lib/components/ui/badge';
	import * as Card from '$lib/components/ui/card';
	import {
		costLabel,
		latencyLabel,
		observationTone,
		runStatusTone,
		type Observation,
		type Tone
	} from '$lib/discovery';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const run = $derived(data.runState.run);
	const items = $derived(data.observationsState.items);
	const hasOlderObservations = $derived(data.observationsState.nextCursor !== null);
	const isLive = $derived(run?.status === 'queued' || run?.status === 'running');
	// The backend may blip while a run executes; that must read as
	// "retrying", not as a dead end.
	const unreachableWhileLive = $derived(!data.runState.apiReachable && isLive);

	const POLL_BASE_MS = 3000;
	const POLL_MAX_MS = 15000;

	let pollAttempts = $state(0);

	const failureCounts = $derived.by(() => {
		const counts = new Map<string, number>();
		for (const item of items) {
			if (!item.failureClass) {
				continue;
			}
			counts.set(item.failureClass, (counts.get(item.failureClass) ?? 0) + 1);
		}
		return [...counts.entries()].sort((a, b) => b[1] - a[1]);
	});

	function toneVariant(tone: Tone): 'destructive' | 'outline' {
		return tone === 'danger' ? 'destructive' : 'outline';
	}

	function toneClasses(tone: Tone): string {
		switch (tone) {
			case 'success':
				return 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400';
			case 'warning':
				return 'bg-amber-500/15 text-amber-700 dark:text-amber-400';
			case 'info':
				return 'bg-sky-500/15 text-sky-700 dark:text-sky-400';
			default:
				return '';
		}
	}

	function shortDate(value: string | null): string {
		return value ? value.slice(0, 16).replace('T', ' ') : '—';
	}

	function runLatency(): string {
		if (!run?.startedAt || !run.completedAt) {
			return '—';
		}
		const ms = Date.parse(run.completedAt) - Date.parse(run.startedAt);
		return latencyLabel(Number.isFinite(ms) && ms >= 0 ? ms : null);
	}

	// Poll only while the backend may still change the outcome; stop on
	// terminal statuses. Each consecutive failed poll doubles the delay
	// (3s -> 6s -> 12s -> capped at 15s); a successful answer resets it.
	// The effect tracks pollAttempts itself: at the cap the recomputed delay
	// is equal, but a new attempt still must reschedule a fresh timer.
	$effect(() => {
		if (data.runState.apiReachable) {
			pollAttempts = 0;
		}
	});

	$effect(() => {
		if (!isLive) {
			return;
		}
		const attempts = pollAttempts;
		const delay = Math.min(POLL_BASE_MS * 2 ** Math.min(attempts, 3), POLL_MAX_MS);
		const timer = setTimeout(() => {
			pollAttempts = attempts + 1;
			void invalidate('app:discovery-run');
		}, delay);
		return () => clearTimeout(timer);
	});
</script>

<svelte:head>
	<title>Discovery run · aptori outreach</title>
</svelte:head>

<div class="mx-auto flex w-full max-w-4xl flex-col gap-6 p-6">
	<header class="flex flex-col gap-1">
		<div class="flex items-center justify-between gap-3">
			<h1 class="text-2xl font-semibold tracking-tight">Discovery run</h1>
			{#if run}
				<Badge variant={toneVariant(runStatusTone(run.status))} class={toneClasses(runStatusTone(run.status))}>
					{run.status}
				</Badge>
			{/if}
		</div>
		<p class="text-sm text-muted-foreground">
			Campaign {data.params.campaignId.slice(0, 8)} · run {data.params.runId.slice(0, 8)}
			{#if run}
				· correlation {run.correlationId}
			{/if}
		</p>
	</header>

	{#if unreachableWhileLive}
		<p
			class="rounded-md border border-amber-500/50 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
			role="status"
			data-testid="unreachable-retrying"
		>
			Backend unreachable - retrying...
		</p>
	{:else if data.runState.detail}
		<p
			class="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
			role="alert"
		>
			{data.runState.detail}
		</p>
	{/if}

	{#if failureCounts.length > 0}
		<div class="rounded-md border border-amber-500/50 bg-amber-500/10 px-4 py-3" role="alert">
			<p class="text-sm font-medium text-amber-800 dark:text-amber-300">
				Failures recorded — nothing is hidden:
			</p>
			<ul class="mt-1 flex flex-wrap gap-x-4 text-sm text-amber-800 dark:text-amber-300">
				{#each failureCounts as [failureClass, count] (failureClass)}
					<li>{count} × {failureClass}</li>
				{/each}
			</ul>
		</div>
	{/if}

	{#if run}
		<Card.Root>
			<Card.Header>
				<Card.Title>Run summary</Card.Title>
				<Card.Description>Started and finished exactly as the backend recorded them.</Card.Description>
			</Card.Header>
			<Card.Content class="grid gap-2 text-sm sm:grid-cols-2">
				<p>Started: <span class="font-medium">{shortDate(run.startedAt)}</span></p>
				<p>Completed: <span class="font-medium">{shortDate(run.completedAt)}</span></p>
				<p>Total latency: <span class="font-medium">{runLatency()}</span></p>
				<p>Cost: <span class="font-medium">{costLabel(run)}</span></p>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>Method plan</Card.Title>
				<Card.Description>
					<span data-testid="plan-provider">{run.methodPlan.providerVariant}</span>
					{' '}
					<span data-testid="plan-query-count">{run.methodPlan.queries.length} queries</span>
				</Card.Description>
			</Card.Header>
			<Card.Content>
				<details>
					<summary class="cursor-pointer text-sm text-muted-foreground">Frozen queries</summary>
					<ul class="mt-3 grid gap-2">
						{#each run.methodPlan.queries as query (query.id)}
							<li class="text-sm">
								<span class="font-mono">{query.id}</span>
								{' — '}
								<span>{query.query}</span>
							</li>
						{/each}
					</ul>
				</details>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>Observations</Card.Title>
				<Card.Description>Append-only evidence; rows can never be revised.</Card.Description>
			</Card.Header>
			<Card.Content>
				{#if items.length === 0}
					{#if data.observationsState.detail}
						<p class="text-sm text-destructive" role="alert">{data.observationsState.detail}</p>
					{:else if isLive}
						<p class="text-sm text-muted-foreground" data-testid="observations-empty">
							No observations recorded yet — this page polls while the run executes.
						</p>
					{:else}
						<p class="text-sm text-muted-foreground" data-testid="observations-empty">
							No observations were recorded for this run.
						</p>
					{/if}
				{:else}
					<table class="w-full text-left text-sm">
						<thead class="text-xs uppercase tracking-wide text-muted-foreground">
							<tr>
								<th scope="col" class="py-2 pr-3">Query</th>
								<th scope="col" class="py-2 pr-3">Status</th>
								<th scope="col" class="py-2 pr-3">Failure class</th>
								<th scope="col" class="py-2 pr-3">Reason</th>
								<th scope="col" class="py-2 pr-3">Candidates</th>
								<th scope="col" class="py-2">Latency</th>
							</tr>
						</thead>
						<tbody>
							{#each items as item (item.id)}
								{@const tone = observationTone(item.status)}
								<tr class="border-t">
									<td class="py-2 pr-3 font-mono">{item.queryId}</td>
									<td class="py-2 pr-3">
										<Badge variant={toneVariant(tone)} class={toneClasses(tone)}>
											{item.status}
										</Badge>
									</td>
									<td class="py-2 pr-3 font-medium">
										{#if item.failureClass}
											<span class="text-destructive">{item.failureClass}</span>
										{:else}
											—
										{/if}
									</td>
									<td
										class="max-w-48 truncate py-2 pr-3 text-muted-foreground"
										title={item.failureReason ?? ''}
									>
										{item.failureReason ?? '—'}
									</td>
									<td class="py-2 pr-3">{item.candidateCount}</td>
									<td class="py-2">{latencyLabel(item.elapsedMs)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
				{#if hasOlderObservations}
					<p class="mt-3 text-sm text-muted-foreground" data-testid="older-observations">
						+ older observations hidden
					</p>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
