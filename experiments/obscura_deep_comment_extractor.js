/**
 * Obscura in-origin Reddit thread extraction spike.
 *
 * This runner produces immutable per-run evidence. It does not log in, rotate
 * identities, retry access-control failures, or submit Reddit actions.
 */

const { chromium } = require('playwright-core');
const { execFileSync, spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const DEFAULT_OBSCURA_BIN = '/home/hari/.gemini/antigravity-ide/brain/97af282d-c646-4491-92a4-5745dadb63c0/scratch/obscura';
const OBSCURA_BIN = process.env.OBSCURA_BIN || DEFAULT_OBSCURA_BIN;
const PORT = Number.parseInt(process.env.OBSCURA_PORT || '9230', 10);
const TARGET_URL = process.env.TARGET_URL || 'https://www.reddit.com/r/AskRobotics/comments/1uxx2bs/is_robotics_industry_broken/';
const USE_STEALTH = process.env.OBSCURA_STEALTH === '1';
const OUTPUT_ROOT = process.env.OUTPUT_ROOT || path.join(__dirname, 'runs');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function sha256Text(value) {
    return crypto.createHash('sha256').update(value).digest('hex');
}

function sha256File(filePath) {
    return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function redactUrl(value) {
    const parsed = new URL(value);
    for (const key of ['solution', 'js_challenge', 'token', 'jsc_orig_r']) {
        parsed.searchParams.delete(key);
    }
    return parsed.toString();
}

function redactSensitiveText(value) {
    return value.replace(/((?:solution|js_challenge|token|jsc_orig_r)=)[^&\s:]*/g, '$1<redacted>');
}

function canonicalJsonUrl(value) {
    const parsed = new URL(value);
    if (!['www.reddit.com', 'reddit.com'].includes(parsed.hostname)) {
        throw new Error(`Unsupported target host: ${parsed.hostname}`);
    }
    parsed.hostname = 'www.reddit.com';
    parsed.hash = '';
    parsed.search = '';
    parsed.pathname = `${parsed.pathname.replace(/\/$/, '')}.json`;
    parsed.searchParams.set('limit', '500');
    parsed.searchParams.set('raw_json', '1');
    parsed.searchParams.set('sort', 'confidence');
    return parsed.toString();
}

function readProcessTable() {
    const output = execFileSync('ps', ['-e', '-o', 'pid=,ppid=,rss='], { encoding: 'utf8' });
    return output.trim().split('\n').map(line => {
        const [pid, ppid, rssKB] = line.trim().split(/\s+/).map(Number);
        return { pid, ppid, rssKB };
    }).filter(row => Number.isFinite(row.pid) && Number.isFinite(row.rssKB));
}

function processTreeRssMB(rootPid) {
    try {
        const rows = readProcessTable();
        const included = new Set([rootPid]);
        let changed = true;
        while (changed) {
            changed = false;
            for (const row of rows) {
                if (included.has(row.ppid) && !included.has(row.pid)) {
                    included.add(row.pid);
                    changed = true;
                }
            }
        }
        const rssKB = rows.filter(row => included.has(row.pid)).reduce((sum, row) => sum + row.rssKB, 0);
        return Number((rssKB / 1024).toFixed(2));
    } catch {
        return null;
    }
}

function startMemorySampler(obscuraPid) {
    const samples = [];
    const sample = () => {
        samples.push({
            timestamp: new Date().toISOString(),
            obscuraTreeRssMB: processTreeRssMB(obscuraPid),
            nodeRssMB: Number((process.memoryUsage().rss / 1024 / 1024).toFixed(2)),
        });
    };
    sample();
    const timer = setInterval(sample, 250);
    return {
        stop() {
            clearInterval(timer);
            sample();
            const numeric = key => samples.map(item => item[key]).filter(Number.isFinite);
            const obscuraValues = numeric('obscuraTreeRssMB');
            const nodeValues = numeric('nodeRssMB');
            return {
                sampleIntervalMs: 250,
                sampleCount: samples.length,
                obscuraTreePeakRssMB: obscuraValues.length ? Math.max(...obscuraValues) : null,
                nodePeakRssMB: nodeValues.length ? Math.max(...nodeValues) : null,
                samples,
            };
        },
    };
}

async function connectOverCdpWithRetry(endpoint, processState, timeoutMs = 12_000) {
    const deadline = Date.now() + timeoutMs;
    let lastError;
    while (Date.now() < deadline) {
        if (processState.exitCode !== null) {
            throw new Error(`Obscura exited before CDP became ready (exit ${processState.exitCode})`);
        }
        try {
            return await chromium.connectOverCDP(endpoint);
        } catch (error) {
            lastError = error;
            await sleep(250);
        }
    }
    throw new Error(`CDP did not become ready within ${timeoutMs}ms: ${lastError?.message || 'unknown error'}`);
}

function normalizeThread(data) {
    const postObj = data[0]?.data?.children?.[0]?.data;
    if (!postObj?.id) {
        throw new Error('Reddit response did not contain a root post');
    }

    const post = {
        id: postObj.name || `t3_${postObj.id}`,
        postIdClean: postObj.id,
        title: postObj.title,
        author: postObj.author,
        score: postObj.score,
        upvoteRatio: postObj.upvote_ratio,
        subreddit: postObj.subreddit_name_prefixed,
        totalReportedComments: postObj.num_comments,
        createdUtc: postObj.created_utc,
        createdIso: new Date(postObj.created_utc * 1000).toISOString(),
        selftext: postObj.selftext,
        permalink: postObj.permalink,
    };

    const comments = [];
    const unresolvedMore = [];

    function parseChildren(children, traversalDepth = 0) {
        if (!Array.isArray(children)) return;
        for (const child of children) {
            const item = child?.data;
            if (child?.kind === 't1' && item) {
                comments.push({
                    id: item.name || `t1_${item.id}`,
                    commentIdClean: item.id,
                    author: item.author,
                    score: item.score,
                    depth: Number.isInteger(item.depth) ? item.depth : traversalDepth,
                    parentId: item.parent_id,
                    createdUtc: item.created_utc,
                    createdIso: new Date(item.created_utc * 1000).toISOString(),
                    body: item.body,
                    visibility: item.author === '[deleted]' || item.body === '[deleted]'
                        ? 'deleted'
                        : item.body === '[removed]' ? 'removed' : 'visible',
                });
                parseChildren(item.replies?.data?.children, traversalDepth + 1);
            } else if (child?.kind === 'more' && item) {
                unresolvedMore.push({
                    id: item.id || null,
                    parentId: item.parent_id || null,
                    count: item.count || 0,
                    childIds: Array.isArray(item.children) ? item.children : [],
                    depth: Number.isInteger(item.depth) ? item.depth : traversalDepth,
                });
            }
        }
    }

    parseChildren(data[1]?.data?.children || []);

    const ids = comments.map(comment => comment.id);
    const idSet = new Set(ids);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    const missingParentReferences = comments
        .filter(comment => comment.parentId !== post.id && !idSet.has(comment.parentId))
        .map(comment => ({ id: comment.id, parentId: comment.parentId }));

    return {
        post,
        comments,
        unresolvedMore,
        validation: {
            extractedCommentCount: comments.length,
            uniqueCommentCount: idSet.size,
            duplicateIds,
            missingParentReferences,
            maxDepth: comments.length ? Math.max(...comments.map(comment => comment.depth)) : null,
            unresolvedMoreNodeCount: unresolvedMore.length,
            unresolvedMoreChildCount: unresolvedMore.reduce((sum, item) => sum + item.childIds.length, 0),
            sourceTreeExhausted: unresolvedMore.length === 0,
        },
    };
}

async function extractCompleteRedditThread(url) {
    const runId = `obscura_${new Date().toISOString().replace(/[:.]/g, '-')}_${crypto.randomBytes(4).toString('hex')}`;
    const runDir = path.join(OUTPUT_ROOT, runId);
    fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
    fs.mkdirSync(runDir, { recursive: false });

    const obscuraArgs = ['serve', '--port', PORT.toString(), '--allow-private-network'];
    if (USE_STEALTH) obscuraArgs.push('--stealth');

    console.log(`[1] Starting Obscura (${USE_STEALTH ? 'stealth' : 'standard'}) on port ${PORT}; run ${runId}`);
    const obscuraProc = spawn(OBSCURA_BIN, obscuraArgs, { stdio: ['ignore', 'pipe', 'pipe'] });
    const processState = { exitCode: null };
    const stderr = [];
    obscuraProc.stderr.on('data', chunk => stderr.push(chunk.toString()));
    obscuraProc.on('exit', code => { processState.exitCode = code; });
    const sampler = startMemorySampler(obscuraProc.pid);

    let browser;
    let memoryProfile;
    const startedAt = Date.now();

    try {
        browser = await connectOverCdpWithRetry(`http://127.0.0.1:${PORT}`, processState);
        const context = browser.contexts()[0] || await browser.newContext();
        const page = context.pages()[0] || await context.newPage();

        console.log(`[2] Navigating to ${url}`);
        const navigationResponse = await page.goto(url, { waitUntil: 'load', timeout: 35_000 });
        const finalUrl = redactUrl(page.url());
        const jsonUrl = canonicalJsonUrl(url);

        console.log('[3] Fetching the structured thread response in-origin');
        const rawResponse = await page.evaluate(async endpoint => {
            const response = await fetch(endpoint, { credentials: 'same-origin' });
            return {
                status: response.status,
                statusText: response.statusText,
                contentType: response.headers.get('content-type'),
                body: await response.text(),
            };
        }, jsonUrl);

        fs.writeFileSync(path.join(runDir, 'raw-thread-response.txt'), rawResponse.body);
        if (rawResponse.status < 200 || rawResponse.status >= 300) {
            throw new Error(`Structured thread fetch failed: HTTP ${rawResponse.status} ${rawResponse.statusText}`);
        }
        if (!rawResponse.contentType?.toLowerCase().includes('json')) {
            throw new Error(`Structured thread fetch returned unexpected content type: ${rawResponse.contentType}`);
        }

        let parsed;
        try {
            parsed = JSON.parse(rawResponse.body);
        } catch (error) {
            throw new Error(`Structured thread response was not valid JSON: ${error.message}`);
        }

        const normalized = normalizeThread(parsed);
        memoryProfile = sampler.stop();
        const result = {
            schemaVersion: 1,
            runId,
            startedAt: new Date(startedAt).toISOString(),
            completedAt: new Date().toISOString(),
            elapsedSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(2)),
            accessMode: USE_STEALTH ? 'obscura_cdp_stealth_anonymous' : 'obscura_cdp_standard_anonymous',
            targetUrl: redactUrl(url),
            finalUrl,
            structuredEndpoint: redactUrl(jsonUrl),
            navigationStatus: navigationResponse?.status() || null,
            response: {
                status: rawResponse.status,
                statusText: rawResponse.statusText,
                contentType: rawResponse.contentType,
                bytes: Buffer.byteLength(rawResponse.body),
                sha256: sha256Text(rawResponse.body),
            },
            runtime: {
                wslDistro: process.env.WSL_DISTRO_NAME || null,
                platform: process.platform,
                architecture: process.arch,
                kernel: os.release(),
                nodeVersion: process.version,
                playwrightCoreVersion: require('playwright-core/package.json').version,
                obscuraBinary: OBSCURA_BIN,
                obscuraBinarySha256: sha256File(OBSCURA_BIN),
                obscuraArguments: obscuraArgs,
            },
            memoryProfile,
            ...normalized,
        };

        fs.writeFileSync(path.join(runDir, 'result.json'), JSON.stringify(result, null, 2));
        fs.writeFileSync(path.join(runDir, 'stderr.log'), redactSensitiveText(stderr.join('')));
        console.log(`[+] Extracted ${result.validation.extractedCommentCount} comments; max depth ${result.validation.maxDepth}; unresolved more nodes ${result.validation.unresolvedMoreNodeCount}; ${result.elapsedSeconds}s`);
        console.log(`[+] Evidence saved to ${runDir}`);
        return result;
    } catch (error) {
        if (!memoryProfile) memoryProfile = sampler.stop();
        const failure = {
            schemaVersion: 1,
            runId,
            timestamp: new Date().toISOString(),
            elapsedSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(2)),
            error: error.message,
            accessMode: USE_STEALTH ? 'obscura_cdp_stealth_anonymous' : 'obscura_cdp_standard_anonymous',
            targetUrl: redactUrl(url),
            memoryProfile,
        };
        fs.writeFileSync(path.join(runDir, 'failure.json'), JSON.stringify(failure, null, 2));
        fs.writeFileSync(path.join(runDir, 'stderr.log'), redactSensitiveText(stderr.join('')));
        throw error;
    } finally {
        if (browser) await browser.close().catch(() => {});
        if (obscuraProc.exitCode === null) obscuraProc.kill('SIGTERM');
    }
}

if (require.main === module) {
    extractCompleteRedditThread(TARGET_URL).catch(error => {
        console.error(`Fatal error: ${error.message}`);
        process.exitCode = 1;
    });
}

module.exports = { canonicalJsonUrl, extractCompleteRedditThread, normalizeThread, redactSensitiveText, redactUrl };
