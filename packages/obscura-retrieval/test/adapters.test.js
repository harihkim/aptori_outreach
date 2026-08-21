const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const { ObscuraDuckDuckGoLiteDiscoverySource } = require('../src/discovery.js');
const { ObscuraRedditThreadFetcher } = require('../src/thread-fetcher.js');

function config() {
    return {
        providerVariant: 'test-thread',
        configSha256: 'a'.repeat(64),
        thread: { commentLimit: 500, sort: 'confidence', minimumGapMs: 0 },
    };
}

function runtimeWithPage(page) {
    return {
        async runPage(targetUrl, handler) {
            return handler({
                page,
                navigationResponse: { status: () => 200 },
                network: { requests: 1, responses: 1, failedRequests: 0, transferredResponseBytes: 0 },
            });
        },
        describe() { return { test: true }; },
    };
}

test('thread fetch stops before structured fetch when navigation enters a challenge', async t => {
    const outputRoot = fs.mkdtempSync('/tmp/aptori-obscura-blocked-');
    t.after(() => fs.rmSync(outputRoot, { recursive: true, force: true }));
    let evaluateCount = 0;
    const page = {
        url: () => 'https://www.reddit.com/r/test/comments/abc/title/?js_challenge=secret&keep=yes',
        async evaluate() {
            evaluateCount += 1;
            return { title: 'Reddit', visibleText: '' };
        },
    };
    const adapter = new ObscuraRedditThreadFetcher({
        config: config(),
        runtime: runtimeWithPage(page),
        outputRoot,
    });

    const observation = await adapter.fetchThread({
        id: 'blocked',
        url: 'https://www.reddit.com/r/test/comments/abc/title/',
    });

    assert.equal(evaluateCount, 1, 'structured fetch evaluate must never execute');
    assert.equal(observation.status, 'blocked');
    assert.equal(observation.rawArtifact, null);
    assert.equal(observation.finalUrl, 'https://www.reddit.com/r/test/comments/abc/title/?keep=yes');
    assert.equal(fs.readdirSync(observation.evidenceDirectory).includes('raw-thread-response.json'), false);
});

test('discovery retains a typed block but not challenge HTML', async t => {
    const outputRoot = fs.mkdtempSync('/tmp/aptori-obscura-discovery-blocked-');
    t.after(() => fs.rmSync(outputRoot, { recursive: true, force: true }));
    const page = {
        url: () => 'https://lite.duckduckgo.com/lite/?q=test',
        async evaluate() {
            return {
                title: 'Blocked',
                visibleText: "You've been blocked",
                rows: [{ href: 'https://www.reddit.com/r/test/comments/abc/title/', title: 'Should not escape' }],
                html: '<html>challenge data</html>',
            };
        },
    };
    const discoveryConfig = {
        providerVariant: 'test-discovery',
        configSha256: 'b'.repeat(64),
        discovery: { maxCandidates: 50, minimumGapMs: 0 },
    };
    const adapter = new ObscuraDuckDuckGoLiteDiscoverySource({
        config: discoveryConfig,
        runtime: runtimeWithPage(page),
        outputRoot,
    });

    const observation = await adapter.discover({ id: 'blocked', query: 'test', subreddits: [] });

    assert.equal(observation.status, 'blocked');
    assert.equal(observation.rawArtifact, null);
    assert.equal(observation.candidateCount, 0);
    assert.equal(fs.readdirSync(observation.evidenceDirectory).includes('raw-page.html'), false);
});

test('thread fetch writes raw evidence before returning a normalized success', async t => {
    const outputRoot = fs.mkdtempSync('/tmp/aptori-obscura-success-');
    t.after(() => fs.rmSync(outputRoot, { recursive: true, force: true }));
    const payload = [
        { data: { children: [{ kind: 't3', data: { id: 'abc', name: 't3_abc', title: 'Title', author: 'op', score: 1, upvote_ratio: 1, subreddit_name_prefixed: 'r/test', num_comments: 1, created_utc: 1, selftext: 'Body', permalink: '/r/test/comments/abc/title/', is_self: true } }] } },
        { data: { children: [{ kind: 't1', data: { id: 'comment', name: 't1_comment', author: 'person', score: 1, depth: 0, parent_id: 't3_abc', created_utc: 2, body: 'Reply', replies: '' } }] } },
    ];
    let evaluateCount = 0;
    const page = {
        url: () => 'https://www.reddit.com/r/test/comments/abc/title/',
        async evaluate() {
            evaluateCount += 1;
            if (evaluateCount === 1) return { title: 'Title', visibleText: 'Body' };
            return {
                status: 200,
                statusText: 'OK',
                contentType: 'application/json; charset=UTF-8',
                body: JSON.stringify(payload),
            };
        },
    };
    const adapter = new ObscuraRedditThreadFetcher({
        config: config(),
        runtime: runtimeWithPage(page),
        outputRoot,
    });

    const observation = await adapter.fetchThread({
        id: 'success',
        url: 'https://www.reddit.com/r/test/comments/abc/title/',
    });

    assert.equal(evaluateCount, 2);
    assert.equal(observation.status, 'success');
    assert.equal(observation.normalized.validation.sourceTreeExhausted, true);
    assert.equal(fs.existsSync(observation.rawArtifact.path), true);
    assert.match(observation.normalizedSha256, /^[a-f0-9]{64}$/);
});
