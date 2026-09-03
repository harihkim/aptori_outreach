<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { Badge } from '$lib/components/ui/badge';
	import * as Card from '$lib/components/ui/card';
	import {
		costLabel,
		latencyLabel,
		observationTone,
		runStatusTone,
		usageLabel,
		type Observation,
		type Tone
	} from '$lib/discovery';
	import { DISCOVERY_EVENT_TYPES, parseDiscoveryEvent } from '$lib/discovery-events';
	import type { Attachment } from 'svelte/attachments';
	import type { PageData } from './$types';
	import { startDiscoveryRunPolling } from './polling';

	let { data }: { data: PageData } = $props();

	const run = $derived(data.runState.run);
	const items = $derived(data.observationsState.items);
	const hasOlderObservations = $derived(data.observationsState.nextCursor !== null);
	const transitions = $derived(data.conversationsState.items);
	// A run is live while discovery executes, and afterwards until the
	// backend durably reports Candidate-to-Conversation processing complete.
	// An unreadable transition answer (not found, unreachable, malformed)
	// is not evidence that work remains, so it never keeps the page live by
	// itself; sticky state below covers transient outages of a known-live run.
	const transitionsKnown = $derived(data.conversationsState.detail === null);
	const isLive = $derived(
		run?.status === 'queued' ||
			run?.status === 'running' ||
			(run !== null && transitionsKnown && !data.conversationsState.processingComplete)
	);
	// Preserve last-known live status across transient unreachable polls so
	// polling does not permanently stop and the retrying banner can render.
	// svelte-ignore state_referenced_locally: initial value intentionally captures mount-time live.
	let stickyLive = $state(isLive);
	$effect(() => {
		if (isLive) {
			stickyLive = true;
		} else if (run !== null && data.conversationsState.processingComplete) {
			// run is non-null, terminal, and processing is durably complete —
			// this is an authoritative value.
			stickyLive = false;
		}
	});
	const effectiveLive = $derived(stickyLive || isLive);
	let streamConnected = $state(false);
	let streamUnavailable = $state(false);
	const effectivePollingLive = $derived(effectiveLive && !streamConnected);
	// The backend may blip while a run executes; that must read as
	// "retrying", not as a dead end.
	const unreachableWhileLive = $derived(!data.runState.apiReachable && effectiveLive);

	// EventSource cannot send the private backend token, so this connects to
	// the same-origin SvelteKit proxy. Polling remains armed until the stream
	// opens and is re-enabled immediately when the stream errors or closes.
	const liveRunId = $derived(run?.id ?? null);
	const liveCorrelationId = $derived(run?.correlationId ?? null);
	$effect(() => {
		const currentRunId = liveRunId;
		const currentCorrelationId = liveCorrelationId;
		const live = effectiveLive;
		if (!currentRunId || !currentCorrelationId || !live) {
			streamConnected = false;
			streamUnavailable = false;
			return;
		}
		if (typeof EventSource === 'undefined') {
			streamConnected = false;
			streamUnavailable = true;
			return;
		}

		const source = new EventSource(`/api/discovery-runs/${currentRunId}/events`);
		let disposed = false;
		const handleEvent = (event: Event) => {
			if (disposed) {
				return;
			}
			const message = event as MessageEvent<string>;
			const progress = parseDiscoveryEvent(message.type, message.data);
			if (
				!progress ||
				progress.runId !== currentRunId ||
				progress.correlationId !== currentCorrelationId
			) {
				return;
			}
			// The API remains authoritative; an event only prompts a fresh
			// server load, so a malformed/stale message cannot mutate state.
			void invalidate('app:discovery-run');
			if (progress.type === 'conversation.processing_completed') {
				streamConnected = false;
				source.close();
			}
		};

		for (const eventType of DISCOVERY_EVENT_TYPES) {
			source.addEventListener(eventType, handleEvent);
		}
		source.onopen = () => {
			if (!disposed) {
				streamConnected = true;
				streamUnavailable = false;
			}
		};
		source.onerror = () => {
			if (!disposed) {
				streamConnected = false;
				streamUnavailable = true;
				source.close();
			}
		};

		return () => {
			disposed = true;
			source.close();
			streamConnected = false;
		};
	});

	const failureCounts = $derived.by(() => {
		const counts: Record<string, number> = Object.create(null);
		for (const item of items) {
			if (!item.failureClass) {
				continue;
			}
			counts[item.failureClass] = (counts[item.failureClass] ?? 0) + 1;
		}
		return Object.entries(counts).sort((a, b) => b[1] - a[1]);
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

	// The attachment re-runs whenever reachability or liveness changes,
	// tearing down the previous chain; each fresh chain starts its local
	// attempt counter at zero, so a reachable backend resets the backoff,
	// a terminal status never schedules, and unmount clears the timer.
	// Use sticky live so transient unreachable does not kill polling.
	const attachPolling: Attachment = () =>
		startDiscoveryRunPolling(
			() => ({ live: effectivePollingLive, reachable: data.runState.apiReachable }),
			() => {
				void invalidate('app:discovery-run');
			}
		);
</script>

<svelte:head>
	<title>Discovery run · aptori outreach</title>
</svelte:head>

<div class="mx-auto flex w-full max-w-4xl flex-col gap-6 p-6" {@attach attachPolling}>
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
	{#if effectiveLive}
		<p class="text-xs text-muted-foreground" role="status" data-testid="progress-transport">
			{#if streamConnected}
				Live progress connected
			{:else if streamUnavailable}
				Live progress unavailable — polling fallback active
			{:else}
				Connecting to live progress…
			{/if}
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
				{#if usageLabel(run)}
					<p>Measured usage: <span class="font-medium">{usageLabel(run)}</span></p>
				{/if}
				<p>Currency cost: <span class="font-medium">{costLabel(run)}</span></p>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>Method plan</Card.Title>
				<Card.Description>
					<span data-testid="plan-provider">{run.methodPlan.providerVariant}</span>
					&#32;
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
								&#32;—&#32;
								<span>{query.query}</span>
							</li>
						{/each}
					</ul>
				</details>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>Candidates to Conversations</Card.Title>
				<Card.Description>
					{data.conversationsState.normalizedCount} of {data.conversationsState.expectedCount}
					candidates normalized from retained evidence.
				</Card.Description>
			</Card.Header>
			<Card.Content>
				{#if data.conversationsState.detail}
					<p class="text-sm text-destructive" role="alert">{data.conversationsState.detail}</p>
				{:else if transitions.length === 0}
					<p class="text-sm text-muted-foreground">No candidates found yet.</p>
				{:else}
					<ul class="grid gap-3" data-testid="candidate-conversation-list">
						{#each transitions as transition (transition.externalSourceId)}
							<li class="rounded-md border p-3">
								<div class="flex items-start justify-between gap-3">
									<div class="min-w-0">
										<a
											class="line-clamp-2 font-medium hover:underline"
											href={transition.url}
											data-sveltekit-reload
											rel="noopener noreferrer"
										>
											{transition.title || transition.externalSourceId}
										</a>
										<p class="mt-1 font-mono text-xs text-muted-foreground">
											{transition.externalSourceId}
										</p>
									</div>
									<Badge variant="outline">
										{transition.state === 'conversation' ? 'Conversation' : 'Candidate'}
									</Badge>
								</div>
								{#if transition.conversation}
									<p class="mt-2 text-xs text-muted-foreground">
										{transition.conversation.currentVersion.normalizerVersion} ·
										{transition.conversation.currentVersion.normalizedContentSha256.slice(0, 12)}
										{transition.conversation.currentVersion.sourceTreeExhausted ? ' · complete tree' : ' · incomplete tree'}
									</p>
								{:else if transition.retrievalStatus}
									<p class="mt-2 text-xs text-muted-foreground">Fetch: {transition.retrievalStatus}</p>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
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
