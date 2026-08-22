<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { nextActions, type Campaign, type PromotionPosture } from '$lib/campaigns';
	import type { ActionData, PageData } from './$types';

	let { data, form = null }: { data: PageData; form?: ActionData } = $props();

	const postures: { value: PromotionPosture; label: string }[] = [
		{ value: 'expertise_first', label: 'Expertise first' },
		{ value: 'balanced', label: 'Balanced' },
		{ value: 'high_intent_only', label: 'High-intent product mentions only' }
	];

	function postureLabel(value: PromotionPosture): string {
		return postures.find((posture) => posture.value === value)?.label ?? value;
	}

	function createdOn(campaign: Campaign): string {
		return campaign.createdAt.slice(0, 10);
	}

	function statusVariant(status: Campaign['status']): 'secondary' | 'outline' {
		return status === 'active' ? 'secondary' : 'outline';
	}

	function claimPolicy(campaign: Campaign): string | null {
		const total = campaign.approvedClaims.length + campaign.prohibitedClaims.length;
		if (total === 0) {
			return null;
		}
		return `Claim policy: ${campaign.approvedClaims.length} approved, ${campaign.prohibitedClaims.length} prohibited`;
	}

	function fieldId(field: string, suffix: string): string {
		return suffix === '' ? field : `${field}-${suffix}`;
	}

	// A failed submission echoes its key back so retrying replays it instead
	// of creating a second write; fresh keys otherwise.
	let submissionKey = $derived(
		form && 'idempotency_key' in form && typeof form.idempotency_key === 'string'
			? form.idempotency_key
			: crypto.randomUUID()
	);
</script>

<svelte:head>
	<title>Campaigns · aptori outreach</title>
</svelte:head>

{#snippet formFields(suffix: string, campaign: Campaign | null)}
	<div class="grid gap-1.5">
		<label for={fieldId('name', suffix)} class="text-sm font-medium">Name</label>
		<input id={fieldId('name', suffix)} name="name" required maxlength="200"
			class="input" value={campaign?.name ?? ''} />
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('product_context', suffix)} class="text-sm font-medium">Product context</label>
		<textarea id={fieldId('product_context', suffix)} name="product_context" rows="3"
			class="input" placeholder="What the product does and for whom"
			value={campaign?.productContext ?? ''}></textarea>
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('icp', suffix)} class="text-sm font-medium">Audience (ICP)</label>
		<input id={fieldId('icp', suffix)} name="icp" class="input"
			placeholder="Security engineers at API-first companies" value={campaign?.icp ?? ''} />
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('keywords', suffix)} class="text-sm font-medium">Keywords</label>
		<textarea id={fieldId('keywords', suffix)} name="keywords" rows="2" class="input"
			placeholder="One keyword per line" value={campaign?.keywords.join('\n') ?? ''}></textarea>
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('subreddits', suffix)} class="text-sm font-medium">Subreddits</label>
		<textarea id={fieldId('subreddits', suffix)} name="subreddits" rows="2" class="input"
			placeholder="One subreddit per line" value={campaign?.subreddits.join('\n') ?? ''}></textarea>
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('competitors', suffix)} class="text-sm font-medium">Competitors</label>
		<textarea id={fieldId('competitors', suffix)} name="competitors" rows="2" class="input"
			placeholder="One competitor per line - names may contain commas"
			value={campaign?.competitors.join('\n') ?? ''}></textarea>
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('approved_claims', suffix)} class="text-sm font-medium">Approved claims</label>
		<textarea id={fieldId('approved_claims', suffix)} name="approved_claims" rows="2"
			class="input" placeholder="One claim per line - claims may contain commas"
			value={campaign?.approvedClaims.join('\n') ?? ''}></textarea>
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('prohibited_claims', suffix)} class="text-sm font-medium">Prohibited claims</label>
		<textarea id={fieldId('prohibited_claims', suffix)} name="prohibited_claims" rows="2"
			class="input" placeholder="One claim per line - claims may contain commas"
			value={campaign?.prohibitedClaims.join('\n') ?? ''}></textarea>
	</div>
	<div class="grid gap-1.5">
		<label for={fieldId('promotion_posture', suffix)} class="text-sm font-medium">Promotion posture</label>
		<select id={fieldId('promotion_posture', suffix)} name="promotion_posture" class="input">
			{#each postures as posture (posture.value)}
				<option value={posture.value} selected={campaign !== null && posture.value === campaign.promotionPosture}>
					{posture.label}
				</option>
			{/each}
		</select>
	</div>
{/snippet}

<div class="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
	<header class="flex flex-col gap-1">
		<h1 class="text-2xl font-semibold tracking-tight">Campaigns</h1>
		<p class="text-sm text-muted-foreground">
			Research objectives: positioning, constraints, and lifecycle for each Campaign.
		</p>
	</header>

	{#if data.detail}
		<p class="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
			{data.detail}
		</p>
	{/if}
	{#if form?.message}
		<p class="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
			{form.message}
		</p>
	{/if}

	<Card.Root>
		<Card.Header>
			<Card.Title>New campaign</Card.Title>
			<Card.Description>
				Describe the product, audience, and what may be said on its behalf.
			</Card.Description>
		</Card.Header>
		<Card.Content>
			<form method="POST" action="?/create" class="grid gap-4">
				<input type="hidden" name="idempotency_key" value={submissionKey} />
				{@render formFields('', null)}
				<Button type="submit">Create campaign</Button>
			</form>
		</Card.Content>
	</Card.Root>

	<section class="flex flex-col gap-4" aria-label="Campaign list">
		{#each data.campaigns as campaign (campaign.id)}
			<Card.Root class={campaign.status === 'archived' ? 'opacity-60' : ''}>
				<Card.Header>
					<div class="flex items-center justify-between gap-2">
						<Card.Title>{campaign.name}</Card.Title>
						<Badge variant={statusVariant(campaign.status)}>{campaign.status}</Badge>
					</div>
					<Card.Description>
						{postureLabel(campaign.promotionPosture)} · created {createdOn(campaign)}
					</Card.Description>
				</Card.Header>
				<Card.Content class="flex flex-col gap-3">
					{#if campaign.keywords.length > 0}
						<div class="flex flex-wrap gap-1">
							{#each campaign.keywords as keyword (keyword)}
								<Badge variant="outline">{keyword}</Badge>
							{/each}
						</div>
					{/if}
					{#if claimPolicy(campaign)}
						<p class="text-sm text-muted-foreground">{claimPolicy(campaign)}</p>
					{/if}

					{#if campaign.status !== 'archived'}
						<div class="flex flex-wrap gap-2">
							{#each nextActions(campaign.status) as action (action.status)}
								<form method="POST" action="?/transition">
									<input type="hidden" name="campaign_id" value={campaign.id} />
									<input type="hidden" name="idempotency_key" value={submissionKey} />
									<input type="hidden" name="status" value={action.status} />
									<Button
										type="submit"
										variant={action.status === 'archived' ? 'outline' : 'secondary'}
										size="sm"
									>
										{action.label}
									</Button>
								</form>
							{/each}
						</div>
						<details>
							<summary class="cursor-pointer text-sm text-muted-foreground">Edit</summary>
							<form method="POST" action="?/update" class="mt-3 grid gap-4">
								<input type="hidden" name="campaign_id" value={campaign.id} />
								<input type="hidden" name="idempotency_key" value={submissionKey} />
								{@render formFields(campaign.id, campaign)}
								<Button type="submit" variant="outline" size="sm">Save changes</Button>
							</form>
						</details>
					{/if}
				</Card.Content>
			</Card.Root>
		{:else}
			{#if data.detail === null}
				<p class="text-sm text-muted-foreground">No campaigns yet.</p>
			{/if}
		{/each}
	</section>
</div>
