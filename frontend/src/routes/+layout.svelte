<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="min-h-svh">
	<nav class="border-b">
		<div class="mx-auto flex w-full max-w-3xl items-center gap-4 px-6 py-3 text-sm">
			<a href="/" class="font-semibold tracking-tight">aptori outreach</a>
			<a href="/campaigns" class="text-muted-foreground hover:text-foreground">Campaigns</a>
		</div>
	</nav>
	{@render children()}
</div>
