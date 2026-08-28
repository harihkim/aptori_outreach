const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const { readProviderConfig, validateConfigShape } = require('../src/config.js');
const { buildDuckDuckGoLiteUrl } = require('../src/discovery.js');
const { canonicalJson } = require('../src/json.js');
const { classifyError, classifyPageAccess, redactSensitiveText, redactUrl } = require('../src/status.js');

function validConfig() {
    return {
        schemaVersion: 1,
        providerVariant: 'test',
        capability: 'discovery',
        accessMode: 'obscura_cdp_standard_anonymous',
        obscura: {
            version: '0.2.0',
            binaryPath: '/tmp/obscura',
            binarySha256: 'a'.repeat(64),
            stealth: false,
            proxy: null,
            storageDir: null,
            workers: 1,
            maxConnections: 1,
        },
        runtime: {
            environment: 'WSL',
            nodeVersion: 'v20.18.0',
            playwrightCoreVersion: '1.62.1',
        },
        discovery: {
            minimumGapMs: 100,
            maxCandidates: 10,
        },
    };
}

const PROVIDER_CONFIG_ROOT = path.resolve(__dirname, '../../../retrieval-eval/prototype-smoke/provider-configs');

function readConfigFixture(filename) {
    return JSON.parse(fs.readFileSync(path.join(PROVIDER_CONFIG_ROOT, filename), 'utf8'));
}

test('provider config capability selects exactly one matching adapter section', () => {
    const discoveryPath = path.join(PROVIDER_CONFIG_ROOT, 'obscura-duckduckgo-lite.json');
    const threadPath = path.join(PROVIDER_CONFIG_ROOT, 'obscura-reddit-thread.json');
    assert.equal(readProviderConfig(discoveryPath).capability, 'discovery');
    assert.equal(readProviderConfig(threadPath).capability, 'thread_fetch');

    const discovery = readConfigFixture('obscura-duckduckgo-lite.json');
    const thread = readConfigFixture('obscura-reddit-thread.json');
    assert.equal(validateConfigShape({ ...discovery, thread: null }).capability, 'discovery');
    assert.equal(validateConfigShape({ ...thread, discovery: null }).capability, 'thread_fetch');

    for (const [mutate, message] of [
        [config => { delete config.capability; }, /capability must be discovery or thread_fetch/],
        [config => { config.capability = 'unknown'; }, /capability must be discovery or thread_fetch/],
        [config => { config.capability = 'thread_fetch'; }, /thread_fetch capability requires thread/],
        [config => { config.thread = { minimumGapMs: 1, commentLimit: 1, sort: 'confidence' }; }, /discovery capability must not define thread/],
        [config => { delete config.discovery; }, /discovery capability requires discovery/],
    ]) {
        const config = readConfigFixture('obscura-duckduckgo-lite.json');
        mutate(config);
        assert.throws(() => validateConfigShape(config), message);
    }

    for (const [mutate, message] of [
        [config => { config.capability = 'discovery'; }, /discovery capability requires discovery/],
        [config => { config.discovery = { minimumGapMs: 1, maxCandidates: 1 }; }, /thread_fetch capability must not define discovery/],
        [config => { delete config.thread; }, /thread_fetch capability requires thread/],
    ]) {
        const config = readConfigFixture('obscura-reddit-thread.json');
        mutate(config);
        assert.throws(() => validateConfigShape(config), message);
    }
});

test('provider config loading rejects a capability mismatch before runtime startup', () => {
    const discoveryPath = path.join(PROVIDER_CONFIG_ROOT, 'obscura-duckduckgo-lite.json');
    assert.throws(
        () => readProviderConfig(discoveryPath, { requiredCapability: 'thread_fetch' }),
        /Provider config capability mismatch: expected thread_fetch, got discovery/,
    );
});

test('retrieval CLI rejects wrong-command configs before reading input or starting runtime', () => {
    const cliPath = path.resolve(__dirname, '../bin/retrieval-cli.js');
    for (const [command, filename, expected, actual] of [
        ['discover', 'obscura-reddit-thread.json', 'discovery', 'thread_fetch'],
        ['fetch-thread', 'obscura-duckduckgo-lite.json', 'thread_fetch', 'discovery'],
    ]) {
        const result = spawnSync(process.execPath, [
            cliPath,
            command,
            '--config', path.join(PROVIDER_CONFIG_ROOT, filename),
            '--input', '/tmp/aptori-r0-input-must-not-be-read.json',
            '--output-root', '/tmp/aptori-r0-output-must-not-be-created',
            '--id', 'test-id',
        ], { encoding: 'utf8' });

        assert.ifError(result.error);
        assert.equal(result.status, 1);
        assert.match(result.stderr, new RegExp(`expected ${expected}, got ${actual}`));
        assert.doesNotMatch(result.stderr, /ENOENT|runtime|Obscura/i);
    }
});

test('config rejects every access mechanism outside ADR-012', () => {
    assert.equal(validateConfigShape(validConfig()).providerVariant, 'test');
    for (const mutate of [
        config => { config.obscura.stealth = true; },
        config => { config.obscura.proxy = 'http://proxy'; },
        config => { config.obscura.storageDir = '/tmp/profile'; },
        config => { config.accessMode = 'authenticated'; },
        config => { config.runtime.environment = 'linux'; },
    ]) {
        const config = validConfig();
        mutate(config);
        assert.throws(() => validateConfigShape(config));
    }
});

test('discovery query is always Reddit-thread scoped', () => {
    const scoped = buildDuckDuckGoLiteUrl({ id: 'q1', query: 'API security', subreddits: ['cybersecurity'] });
    assert.equal(scoped.query, 'site:reddit.com/r/cybersecurity/comments API security');
    assert.equal(new URL(scoped.url).hostname, 'lite.duckduckgo.com');
    assert.equal(new URL(scoped.url).searchParams.get('q'), scoped.query);
});

test('access and transport outcomes remain explicit', () => {
    assert.deepEqual(classifyPageAccess({ status: 429, url: 'https://x.test/', title: '', visibleText: '' }), {
        status: 'rate_limited',
        reason: 'HTTP 429',
    });
    assert.equal(classifyPageAccess({ status: 200, url: 'https://x.test/?js_challenge=x', title: '', visibleText: '' }).status, 'blocked');
    assert.equal(classifyError(new Error('navigation timeout')).status, 'upstream_unavailable');
    assert.equal(classifyError(new Error('response was not valid JSON')).status, 'parse_failed');
    assert.equal(
        redactUrl('https://www.reddit.com/x?solution=abc&token=secret&keep=yes'),
        'https://www.reddit.com/x?keep=yes',
    );
    assert.doesNotMatch(redactSensitiveText('token=secret&keep=yes'), /secret/);
});

test('canonical JSON sorts nested object keys', () => {
    assert.equal(canonicalJson({ z: 1, a: { d: 2, b: 1 } }), '{"a":{"b":1,"d":2},"z":1}');
});
