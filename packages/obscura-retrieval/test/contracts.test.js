const assert = require('node:assert/strict');
const test = require('node:test');

const { validateConfigShape } = require('../src/config.js');
const { buildDuckDuckGoLiteUrl } = require('../src/discovery.js');
const { canonicalJson } = require('../src/json.js');
const { classifyError, classifyPageAccess, redactSensitiveText, redactUrl } = require('../src/status.js');

function validConfig() {
    return {
        schemaVersion: 1,
        providerVariant: 'test',
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
    };
}

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
