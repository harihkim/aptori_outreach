const fs = require('node:fs');

const { createAttempt, writeObservation, writeRawArtifact } = require('./evidence.js');
const { canonicalizeRedditThreadUrl, normalizeThread, redditJsonUrl } = require('./reddit.js');
const { classifyError, classifyPageAccess, redactUrl } = require('./status.js');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function replayThreadArtifact(rawArtifactPath) {
    const raw = fs.readFileSync(rawArtifactPath, 'utf8');
    return normalizeThread(JSON.parse(raw));
}

class ObscuraRedditThreadFetcher {
    constructor({ config, runtime, outputRoot }) {
        this.config = config;
        this.runtime = runtime;
        this.outputRoot = outputRoot;
        this.lastAttemptStartedMs = 0;
    }

    async fetchThread(input) {
        const waitMs = Math.max(0, this.config.thread.minimumGapMs - (Date.now() - this.lastAttemptStartedMs));
        if (waitMs) await sleep(waitMs);
        this.lastAttemptStartedMs = Date.now();
        const startedAt = new Date().toISOString();
        const startedMs = Date.now();
        // Create attempt before URL validation so even malformed inputs
        // persist a classified observation (ADR-012 invariant).
        const attempt = createAttempt(this.outputRoot, 'thread-fetch', input.id || 'unknown');
        let canonical;
        let structuredEndpoint;
        try {
            canonical = canonicalizeRedditThreadUrl(input.url);
            structuredEndpoint = redditJsonUrl(canonical.url, this.config.thread);
            // Fall through to page fetch inside same try so even
            // canonicalization failures persist evidence.
            const pageResult = await this.runtime.runPage(canonical.url, async ({ page, navigationResponse, network }) => {
                const pageState = await page.evaluate(() => ({
                    title: document.title,
                    visibleText: document.body?.innerText || '',
                }));
                const navigationStatus = navigationResponse?.status() || null;
                const finalUrl = page.url();
                const accessFailure = classifyPageAccess({
                    status: navigationStatus,
                    url: finalUrl,
                    title: pageState.title,
                    visibleText: pageState.visibleText,
                });
                if (accessFailure) {
                    return { navigationStatus, finalUrl, network, pageState, accessFailure, rawResponse: null };
                }
                const rawResponse = await page.evaluate(async endpoint => {
                    const response = await fetch(endpoint, { credentials: 'same-origin' });
                    return {
                        status: response.status,
                        statusText: response.statusText,
                        contentType: response.headers.get('content-type'),
                        body: await response.text(),
                    };
                }, structuredEndpoint);
                return {
                    navigationStatus,
                    finalUrl,
                    network,
                    pageState,
                    accessFailure: null,
                    rawResponse,
                };
            });

            const rawArtifact = pageResult.rawResponse
                ? writeRawArtifact(attempt, 'raw-thread-response.json', pageResult.rawResponse.body)
                : null;
            const accessFailure = pageResult.accessFailure || (pageResult.rawResponse && classifyPageAccess({
                status: pageResult.rawResponse.status,
                url: structuredEndpoint,
                title: '',
                visibleText: '',
            }));

            let normalized = null;
            let status = accessFailure?.status || null;
            let failureReason = accessFailure?.reason || null;
            if (!status && !pageResult.rawResponse?.contentType?.toLowerCase().includes('json')) {
                status = 'parse_failed';
                failureReason = `Unexpected content type: ${pageResult.rawResponse?.contentType || '<missing>'}`;
            }
            if (!status) {
                normalized = normalizeThread(JSON.parse(pageResult.rawResponse.body));
                if (normalized.validation.duplicateIds.length || normalized.validation.missingParentReferences.length) {
                    status = 'parse_failed';
                    failureReason = 'Normalized tree failed identity or parent-reference validation';
                } else {
                    status = normalized.validation.sourceTreeExhausted ? 'success' : 'incomplete';
                }
            }

            const observation = {
                schemaVersion: 1,
                observationId: attempt.attemptId,
                capability: 'thread_fetch',
                providerVariant: this.config.providerVariant,
                configSha256: this.config.configSha256,
                startedAt,
                completedAt: new Date().toISOString(),
                elapsedMs: Date.now() - startedMs,
                status,
                failureReason,
                input: { id: input.id || null, url: canonical.url },
                sourceUrl: canonical.url,
                finalUrl: redactUrl(pageResult.finalUrl),
                externalSourceId: canonical.externalSourceId,
                structuredEndpoint,
                response: {
                    navigationStatus: pageResult.navigationStatus,
                    structuredStatus: pageResult.rawResponse?.status || null,
                    structuredStatusText: pageResult.rawResponse?.statusText || null,
                    contentType: pageResult.rawResponse?.contentType || null,
                },
                rawArtifact,
                normalizedSha256: normalized?.normalizedSha256 || null,
                normalizedContentSha256: normalized?.normalizedContentSha256 || null,
                normalized,
                network: pageResult.network,
                runtime: this.runtime.describe(),
                evidenceDirectory: attempt.directory,
            };
            writeObservation(attempt, observation);
            return observation;
        } catch (error) {
            const failure = classifyError(error);
            const safeUrl = canonical?.url || input.url || '';
            const observation = {
                schemaVersion: 1,
                observationId: attempt.attemptId,
                capability: 'thread_fetch',
                providerVariant: this.config.providerVariant,
                configSha256: this.config.configSha256,
                startedAt,
                completedAt: new Date().toISOString(),
                elapsedMs: Date.now() - startedMs,
                status: failure.status,
                failureReason: failure.reason,
                input: { id: input.id || null, url: safeUrl },
                sourceUrl: safeUrl,
                externalSourceId: canonical?.externalSourceId || null,
                structuredEndpoint: structuredEndpoint || null,
                normalized: null,
                runtime: this.runtime.describe(),
                evidenceDirectory: attempt.directory,
            };
            writeObservation(attempt, observation);
            return observation;
        }
    }
}

module.exports = { ObscuraRedditThreadFetcher, replayThreadArtifact };
