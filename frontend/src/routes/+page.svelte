<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Spinner } from '$lib/components/ui/spinner';

	let { data } = $props();

	let refreshing = $state(false);

	const health = $derived(data.health);
	const apiLabel = $derived(health.apiReachable ? 'connected' : 'unreachable');
	const databaseLabel = $derived(health.database);
	const overallLabel = $derived(health.degraded ? 'degraded' : 'operational');

	async function refresh() {
		refreshing = true;
		try {
			await invalidate('app:health');
		} finally {
			refreshing = false;
		}
	}
</script>

<svelte:head>
	<title>aptori outreach</title>
</svelte:head>

<div class="flex min-h-svh items-center justify-center p-6">
	<Card.Root class="w-full max-w-md">
		<Card.Header>
			<div class="flex items-center justify-between">
				<Card.Title>System status</Card.Title>
				{#if health.degraded}
					<Badge variant="destructive">{overallLabel}</Badge>
				{:else}
					<Badge variant="secondary">{overallLabel}</Badge>
				{/if}
			</div>
			<Card.Description>Live connectivity between this app and the backend API.</Card.Description>
		</Card.Header>
		<Card.Content>
			<div class="flex flex-col gap-4">
				<div class="flex items-center justify-between">
					<span class="text-sm text-muted-foreground">Backend API</span>
					{#if health.apiReachable}
						<Badge variant="secondary">{apiLabel}</Badge>
					{:else}
						<Badge variant="destructive">{apiLabel}</Badge>
					{/if}
				</div>
				<div class="flex items-center justify-between">
					<span class="text-sm text-muted-foreground">Database</span>
					{#if databaseLabel === 'ok'}
						<Badge variant="secondary">{databaseLabel}</Badge>
					{:else if databaseLabel === 'unavailable'}
						<Badge variant="destructive">{databaseLabel}</Badge>
					{:else}
						<Badge variant="outline">{databaseLabel}</Badge>
					{/if}
				</div>
				{#if health.detail}
					<p class="text-sm text-destructive">{health.detail}</p>
				{/if}
			</div>
		</Card.Content>
		<Card.Footer class="flex items-center justify-between">
			<span class="text-xs text-muted-foreground">{health.apiBaseUrl}</span>
			<Button onclick={refresh} disabled={refreshing} variant="outline" size="sm">
				{#if refreshing}
					<Spinner data-icon="inline-start" />
				{/if}
				Refresh
			</Button>
		</Card.Footer>
	</Card.Root>
</div>
