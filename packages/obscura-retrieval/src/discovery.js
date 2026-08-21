const { createAttempt, writeObservation, writeRawArtifact } = require('./evidence.js');
const { sha256Json } = require('./json.js');
const { normalizeDiscoveryRows } = require('./reddit.js');
const { classifyError, classifyPageAccess, redactUrl } = require('./status.js');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function buildDuckDuckGoLiteUrl(input) {
    if (!input?.id || !input?.query) throw new Error('Discovery input requires id and query');
    const subreddits = Array.isArray(input.subreddits) ? input.subreddits.filter(Boolean) : [];
    const siteScope = subreddits.length === 1
        ? `site:reddit.com/r/${subreddits[0]}/comments`
        : 'site:reddit.com comments';
    const query = `${siteScope} ${input.query}`.trim();
    const url = new URL('https://lite.duckduckgo.com/lite/');
    url.searchParams.set('q', query);
    return { url: url.toString(), query };
}

class ObscuraDuckDuckGoLiteDiscoverySource {
    constructor({ config, runtime, outputRoot }) {
        this.config = config;
        this.runtime = runtime;
        this.outputRoot = outputRoot;
        this.lastAttemptStartedMs = 0;
    }

    async discover(input) {
        const waitMs = Math.max(0, this.config.discovery.minimumGapMs - (Date.now() - this.lastAttemptStartedMs));
        if (waitMs) await sleep(waitMs);
        this.lastAttemptStartedMs = Date.now();
        const startedAt = new Date().toISOString();
        const startedMs = Date.now();
        const attempt = createAttempt(this.outputRoot, 'discovery', input.id);
        const target = buildDuckDuckGoLiteUrl(input);

        try {
            const pageResult = await this.runtime.runPage(target.url, async ({ page, navigationResponse, network }) => {
                const pageState = await page.evaluate(() => ({
                    title: document.title,
                    visibleText: document.body?.innerText || '',
                    rows: [...document.querySelectorAll('a.result-link')].map(anchor => {
                        const row = anchor.closest('tr');
                        let cursor = row?.nextElementSibling || null;
                        let snippet = '';
                        let displayedUrl = '';
                        while (cursor && !cursor.querySelector('a.result-link')) {
                            snippet ||= cursor.querySelector('.result-snippet')?.textContent || '';
                            displayedUrl ||= cursor.querySelector('.link-text')?.textContent || '';
                            cursor = cursor.nextElementSibling;
                        }
                        return {
                            href: anchor.href,
                            title: anchor.textContent || '',
                            snippet,
                            displayedUrl,
                        };
                    }),
                    html: document.documentElement.outerHTML,
                }));
                return {
                    navigationStatus: navigationResponse?.status() || null,
                    finalUrl: page.url(),
                    network,
                    ...pageState,
                };
            });

            const accessFailure = classifyPageAccess({
                status: pageResult.navigationStatus,
                url: pageResult.finalUrl,
                title: pageResult.title,
                visibleText: pageResult.visibleText,
            });
            const rawArtifact = accessFailure
                ? null
                : writeRawArtifact(attempt, 'raw-page.html', pageResult.html);
            const candidates = accessFailure ? [] : normalizeDiscoveryRows(pageResult.rows, {
                limit: this.config.discovery.maxCandidates,
            });
            const status = accessFailure?.status || (candidates.length ? 'success' : 'no_results');
            const observation = {
                schemaVersion: 1,
                observationId: attempt.attemptId,
                capability: 'discovery',
                providerVariant: this.config.providerVariant,
                configSha256: this.config.configSha256,
                startedAt,
                completedAt: new Date().toISOString(),
                elapsedMs: Date.now() - startedMs,
                status,
                failureReason: accessFailure?.reason || null,
                input: {
                    id: input.id,
                    pattern: input.pattern || null,
                    query: input.query,
                    subreddits: input.subreddits || [],
                    providerQuery: target.query,
                },
                sourceUrl: target.url,
                finalUrl: redactUrl(pageResult.finalUrl),
                response: { navigationStatus: pageResult.navigationStatus },
                rawArtifact,
                normalizedSha256: sha256Json(candidates),
                candidateCount: candidates.length,
                candidates,
                network: pageResult.network,
                runtime: this.runtime.describe(),
                evidenceDirectory: attempt.directory,
            };
            writeObservation(attempt, observation);
            return observation;
        } catch (error) {
            const failure = classifyError(error);
            const observation = {
                schemaVersion: 1,
                observationId: attempt.attemptId,
                capability: 'discovery',
                providerVariant: this.config.providerVariant,
                configSha256: this.config.configSha256,
                startedAt,
                completedAt: new Date().toISOString(),
                elapsedMs: Date.now() - startedMs,
                status: failure.status,
                failureReason: failure.reason,
                input,
                sourceUrl: target.url,
                candidates: [],
                candidateCount: 0,
                runtime: this.runtime.describe(),
                evidenceDirectory: attempt.directory,
            };
            writeObservation(attempt, observation);
            return observation;
        }
    }
}

module.exports = { ObscuraDuckDuckGoLiteDiscoverySource, buildDuckDuckGoLiteUrl };
