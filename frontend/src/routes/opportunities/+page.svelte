<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import {
		FACTOR_ORDER,
		OPPORTUNITY_STATUSES,
		actionLabel,
		ageLabel,
		factorLabel,
		scoreLabel,
		statusLabel,
		type Opportunity,
		type OpportunityStatus,
		type RecommendedAction
	} from '$lib/opportunities';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let refreshing = $state(false);
	const items = $derived(data.opportunitiesState.items);
	const campaignEntries = $derived(
		Object.entries(data.campaignNames).sort((a, b) => a[1].localeCompare(b[1]))
	);

	function campaignName(id: string): string {
		return data.campaignNames[id] ?? `Campaign ${id.slice(0, 8)}`;
	}

	function actionVariant(action: RecommendedAction): 'secondary' | 'outline' | 'destructive' {
		switch (action) {
			case 'reply_helpfully':
			case 'reply_with_product':
			case 'content_opportunity':
				return 'secondary';
			case 'ignore':
				return 'destructive';
			default:
				return 'outline';
		}
	}

	function percentWidth(value: number): string {
		return `${Math.round(value * 100)}%`;
	}

	function provenance(item: Opportunity): string {
		const run = item.modelRun;
		const model = run.actualModel ?? run.requestedModel ?? 'model unknown';
		const endpoint = run.endpointLabel ? ` via ${run.endpointLabel}` : '';
		const tokens =
			run.inputTokens !== null && run.outputTokens !== null
				? ` · ${run.inputTokens + run.outputTokens} tokens`
				: '';
		return `${run.taskId}@${run.taskVersion} · prompt ${run.promptVersion} · schema ${run.schemaVersion} · ${model}${endpoint} (${run.servedTier} tier)${tokens}`;
	}

	function filterHref(status: OpportunityStatus, campaignId: string | null): string {
		const query = new URLSearchParams({ status });
		if (campaignId) {
			query.set('campaign', campaignId);
		}
		return `/opportunities?${query}`;
	}

	async function refresh(): Promise<void> {
		refreshing = true;
		try {
			await invalidate('app:opportunities');
		} finally {
			refreshing = false;
		}
	}

	const now = new Date();
</script>

<svelte:head>
	<title>Opportunities · aptori outreach</title>
</svelte:head>

<main class="mx-auto grid w-full max-w-3xl gap-6 px-6 py-8">
	<header class="flex flex-wrap items-end justify-between gap-4">
		<div>
			<h1 class="text-2xl font-semibold tracking-tight">Opportunity Inbox</h1>
			<p class="text-sm text-muted-foreground">
				Ranked by the frozen formula v1.0 over typed analysis factors and post age. The model
				never sets the score.
			</p>
		</div>
		<Button variant="outline" size="sm" onclick={refresh} disabled={refreshing}>
			{refreshing ? 'Refreshing…' : 'Refresh'}
		</Button>
	</header>

	<form method="GET" class="flex flex-wrap items-end gap-3" data-testid="inbox-filters">
		<div class="grid gap-1.5">
			<label for="status" class="text-sm font-medium">Status</label>
			<select id="status" name="status" class="input" value={data.filters.status}>
				{#each OPPORTUNITY_STATUSES as status (status)}
					<option value={status}>{statusLabel(status)}</option>
				{/each}
			</select>
		</div>
		<div class="grid gap-1.5">
			<label for="campaign" class="text-sm font-medium">Campaign</label>
			<select id="campaign" name="campaign" class="input" value={data.filters.campaignId ?? ''}>
				<option value="">All campaigns</option>
				{#each campaignEntries as [id, name] (id)}
					<option value={id}>{name}</option>
				{/each}
			</select>
		</div>
		<Button type="submit" variant="outline" size="sm">Apply</Button>
	</form>

	{#if data.opportunitiesState.detail}
		<p class="text-sm text-destructive" role="alert">{data.opportunitiesState.detail}</p>
	{:else if items.length === 0}
		<Card.Root>
			<Card.Content>
				<p class="text-sm text-muted-foreground">
					No {statusLabel(data.filters.status as OpportunityStatus).toLowerCase()} opportunities
					yet. Opportunities appear once a Discovery Run's Conversations have been analyzed.
				</p>
			</Card.Content>
		</Card.Root>
	{:else}
		<ol class="grid gap-4" data-testid="opportunity-list">
			{#each items as item, index (item.id)}
				<li>
					<Card.Root>
						<Card.Header>
							<div class="flex items-start gap-4">
								<div class="min-w-0 flex-1">
									<div class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
										<span>#{index + 1}</span>
										<span>·</span>
										<span>{campaignName(item.campaignId)}</span>
										{#if item.conversation.subreddit}
											<span>·</span>
											<span>{item.conversation.subreddit}</span>
										{/if}
										<span>·</span>
										<span>{ageLabel(item.postCreatedAt, now)}</span>
									</div>
									<Card.Title class="mt-1">
										{#if item.conversation.url}
											<a
												class="hover:underline"
												href={item.conversation.url}
												data-sveltekit-reload
												rel="noopener noreferrer"
											>
												{item.conversation.title || item.conversation.externalId}
											</a>
										{:else}
											{item.conversation.title || item.conversation.externalId}
										{/if}
									</Card.Title>
									<Card.Description>
										{item.analysis.topic}{item.analysis.persona ? ` · ${item.analysis.persona}` : ''}
									</Card.Description>
								</div>
								<div class="text-right">
									<div class="text-2xl font-semibold tabular-nums" data-testid="opportunity-score">
										{scoreLabel(item.opportunityScore)}
									</div>
									<div class="text-xs text-muted-foreground">score · {item.formulaVersion}</div>
								</div>
							</div>
							<div class="mt-2 flex flex-wrap gap-2">
								<Badge variant={actionVariant(item.analysis.recommendedAction)}>
									{actionLabel(item.analysis.recommendedAction)}
								</Badge>
								<Badge variant="outline">{statusLabel(item.status)}</Badge>
								<Badge variant="outline">
									confidence {scoreLabel(item.analysis.factors.confidence)}
								</Badge>
							</div>
						</Card.Header>
						<Card.Content class="grid gap-4">
							<dl class="grid gap-1.5 sm:grid-cols-2" data-testid="factor-breakdown">
								{#each FACTOR_ORDER as factor (factor)}
									<div class="grid gap-0.5">
										<div class="flex justify-between text-xs">
											<dt class="text-muted-foreground">
												{factorLabel(factor)}{factor === 'promotion_fit' ? ' (unscored)' : ''}
											</dt>
											<dd class="tabular-nums">{scoreLabel(item.analysis.factors[factor])}</dd>
										</div>
										<div class="h-1.5 rounded bg-muted" aria-hidden="true">
											<div
												class={factor === 'promotion_fit' ? 'h-1.5 rounded bg-muted-foreground/40' : 'h-1.5 rounded bg-primary'}
												style={`width: ${percentWidth(item.analysis.factors[factor])}`}
											></div>
										</div>
									</div>
								{/each}
							</dl>
							<p class="text-sm">{item.analysis.rationale}</p>
							<p class="font-mono text-xs text-muted-foreground" data-testid="provenance">
								{provenance(item)}
							</p>
						</Card.Content>
					</Card.Root>
				</li>
			{/each}
		</ol>
	{/if}
</main>
