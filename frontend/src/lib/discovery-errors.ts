/** Translate a discovery backend failure into guidance the operator can act on. */
export function explainDiscoveryError(httpStatus: number, body: unknown): string {
	const code = (body as { detail?: { code?: string } } | null)?.detail?.code;
	switch (code) {
		case 'campaign_not_active':
			return 'Only ACTIVE campaigns can run discovery.';
		case 'campaign_not_found':
			return 'Campaign not found.';
		case 'discovery_run_not_found':
			return 'Discovery run not found.';
		case 'worker_queue_unavailable':
			return 'The worker queue is unavailable; retrying the same request will safely re-enqueue.';
		case 'retrieval_inputs_unavailable':
			return 'Retrieval inputs are misconfigured on the backend.';
		case 'unauthorized':
			return 'The backend rejected the request token.';
		case 'api_token_unconfigured':
			return 'The backend has no API token configured.';
		case 'workspace_unconfigured':
			return 'The backend database needs its migrations run.';
		case 'workspace_forbidden':
			return 'The backend token cannot access this workspace.';
		case 'page_cursor_invalid':
			return 'That page link is invalid; return to the newest data.';
		case 'idempotency_key_required':
			return 'The form lost its submission key; refresh and try again.';
		case 'idempotency_key_too_long':
			return 'The form submission key is invalid; refresh and try again.';
		case 'idempotency_key_conflict':
			return 'This submission key was already used for different content.';
		case 'idempotency_key_reconciliation_required':
			return 'This older submission needs operator reconciliation before retrying.';
	}
	if (httpStatus === 422) {
		return 'Some fields were invalid.';
	}
	return `Unexpected error (HTTP ${httpStatus}).`;
}
