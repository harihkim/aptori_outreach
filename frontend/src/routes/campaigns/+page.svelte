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
</script>

<svelte:head>
	<title>Campaigns · aptori outreach</title>
</svelte:head>

<div class="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
	<header class="flex flex-col gap-1">
		<h1 class="text-2xl font-semibold tracking-tight">Campaigns</h1>
		<p class="text-sm text-muted-foreground">
			Research objectives: positioning, constraints, and lifecycle for each listening post.
		</p>
	</header>

	{#if !data.apiReachable}
		<p class="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
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
				<div class="grid gap-1.5">
					<label for="name" class="text-sm font-medium">Name</label>
					<input id="name" name="name" required maxlength="200" class="input" />
				</div>
				<div class="grid gap-1.5">
					<label for="product_context" class="text-sm font-medium">Product context</label>
					<textarea id="product_context" name="product_context" rows="3" class="input"
						placeholder="What the product does and for whom"></textarea>
				</div>
				<div class="grid gap-1.5">
					<label for="icp" class="text-sm font-medium">Audience (ICP)</label>
					<input id="icp" name="icp" class="input" placeholder="Security engineers at API-first companies" />
				</div>
				<div class="grid gap-1.5">
					<label for="keywords" class="text-sm font-medium">Keywords</label>
					<input id="keywords" name="keywords" class="input" placeholder="API security, pentest, CIEM" />
				</div>
				<div class="grid gap-1.5">
					<label for="subreddits" class="text-sm font-medium">Subreddits</label>
					<input id="subreddits" name="subreddits" class="input" placeholder="cybersecurity, netsec" />
				</div>
				<div class="grid gap-1.5">
					<label for="competitors" class="text-sm font-medium">Competitors</label>
					<input id="competitors" name="competitors" class="input" placeholder="Burp Suite, OWASP ZAP" />
				</div>
				<div class="grid gap-1.5">
					<label for="promotion_posture" class="text-sm font-medium">Promotion posture</label>
					<select id="promotion_posture" name="promotion_posture" class="input">
						{#each postures as posture (posture.value)}
							<option value={posture.value}>{posture.label}</option>
						{/each}
					</select>
				</div>
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

					{#if campaign.status !== 'archived'}
						<div class="flex flex-wrap gap-2">
							{#each nextActions(campaign.status) as action (action.status)}
								<form method="POST" action="?/transition">
									<input type="hidden" name="campaign_id" value={campaign.id} />
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
								<div class="grid gap-1.5">
									<label for="name-{campaign.id}" class="text-sm font-medium">Name</label>
									<input id="name-{campaign.id}" name="name" required maxlength="200"
										value={campaign.name} class="input" />
								</div>
								<div class="grid gap-1.5">
									<label for="product_context-{campaign.id}" class="text-sm font-medium">Product context</label>
									<textarea id="product_context-{campaign.id}" name="product_context" rows="3"
										class="input" value={campaign.productContext ?? ''}></textarea>
								</div>
								<div class="grid gap-1.5">
									<label for="icp-{campaign.id}" class="text-sm font-medium">Audience (ICP)</label>
									<input id="icp-{campaign.id}" name="icp" class="input" value={campaign.icp ?? ''} />
								</div>
								<div class="grid gap-1.5">
									<label for="keywords-{campaign.id}" class="text-sm font-medium">Keywords</label>
									<input id="keywords-{campaign.id}" name="keywords" class="input"
										value={campaign.keywords.join(', ')} />
								</div>
								<div class="grid gap-1.5">
									<label for="subreddits-{campaign.id}" class="text-sm font-medium">Subreddits</label>
									<input id="subreddits-{campaign.id}" name="subreddits" class="input"
										value={campaign.subreddits.join(', ')} />
								</div>
								<div class="grid gap-1.5">
									<label for="competitors-{campaign.id}" class="text-sm font-medium">Competitors</label>
									<input id="competitors-{campaign.id}" name="competitors" class="input"
										value={campaign.competitors.join(', ')} />
								</div>
								<div class="grid gap-1.5">
									<label for="promotion_posture-{campaign.id}" class="text-sm font-medium">Promotion posture</label>
									<select id="promotion_posture-{campaign.id}" name="promotion_posture" class="input">
										{#each postures as posture (posture.value)}
											<option value={posture.value} selected={posture.value === campaign.promotionPosture}>
												{posture.label}
											</option>
										{/each}
									</select>
								</div>
								<Button type="submit" variant="outline" size="sm">Save changes</Button>
							</form>
						</details>
					{/if}
				</Card.Content>
			</Card.Root>
		{:else}
			<p class="text-sm text-muted-foreground">No campaigns yet.</p>
		{/each}
	</section>
</div>
