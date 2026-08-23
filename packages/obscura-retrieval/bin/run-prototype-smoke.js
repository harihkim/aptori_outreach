#!/usr/bin/env node

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const {
    ObscuraDuckDuckGoLiteDiscoverySource,
    ObscuraRedditThreadFetcher,
    ObscuraRuntime,
    readProviderConfig,
    replayThreadArtifact,
} = require('../src/index.js');
const { sha256 } = require('../src/json.js');
const { evaluateThreadGate } = require('../src/smoke-gate.js');

const repositoryRoot = path.resolve(__dirname, '../../..');
const smokeRoot = path.join(repositoryRoot, 'retrieval-eval/prototype-smoke');

function readJson(relativePath) {
    return JSON.parse(fs.readFileSync(path.join(smokeRoot, relativePath), 'utf8'));
}

function fileDigest(relativePath) {
    return sha256(fs.readFileSync(path.join(smokeRoot, relativePath)));
}

function assertFrozenWorktree() {
    const status = execFileSync('git', ['status', '--porcelain'], {
        cwd: repositoryRoot,
        encoding: 'utf8',
    }).trim();
    if (status) throw new Error('Prototype smoke requires a clean worktree containing the frozen protocol commit');
    return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repositoryRoot, encoding: 'utf8' }).trim();
}

function summarizeObservation(observation) {
    return {
        observationId: observation.observationId,
        status: observation.status,
        failureReason: observation.failureReason,
        candidateCount: observation.candidateCount,
        externalSourceId: observation.externalSourceId,
        rawArtifact: observation.rawArtifact,
        normalizedSha256: observation.normalizedSha256,
        normalizedContentSha256: observation.normalizedContentSha256,
        validation: observation.normalized?.validation || null,
        elapsedMs: observation.elapsedMs,
    };
}

async function runDiscovery({ config, queries, outputRoot }) {
    const runtime = new ObscuraRuntime(config);
    const observations = [];
    await runtime.start();
    try {
        const adapter = new ObscuraDuckDuckGoLiteDiscoverySource({ config, runtime, outputRoot });
        for (const [index, query] of queries.entries()) {
            process.stdout.write(`[discovery ${index + 1}/${queries.length}] ${query.id}\n`);
            observations.push(await adapter.discover(query));
        }
    } finally {
        await runtime.stop();
    }
    return observations;
}

async function runThreads({ config, threads, outputRoot, runNumber }) {
    const runtime = new ObscuraRuntime(config);
    const observations = [];
    await runtime.start();
    try {
        const adapter = new ObscuraRedditThreadFetcher({ config, runtime, outputRoot });
        for (const [index, thread] of threads.entries()) {
            process.stdout.write(`[thread run ${runNumber} ${index + 1}/${threads.length}] ${thread.id}\n`);
            observations.push(await adapter.fetchThread(thread));
        }
    } finally {
        await runtime.stop();
    }
    return observations;
}

async function main() {
    const sourceCommit = assertFrozenWorktree();
    const protocol = readJson('protocol.json');
    const queryDocument = readJson(protocol.artifacts.queries);
    const threadDocument = readJson(protocol.artifacts.knownThreads);
    if (queryDocument.queries.length !== protocol.discoveryGate.queryCount) throw new Error('Frozen query count does not match protocol');
    if (threadDocument.threads.length !== protocol.threadGate.threadCount) throw new Error('Frozen thread count does not match protocol');

    const discoveryConfig = readProviderConfig(path.join(smokeRoot, protocol.artifacts.discoveryConfig));
    const threadConfig = readProviderConfig(path.join(smokeRoot, protocol.artifacts.threadConfig));
    const runId = `${protocol.evaluationId}_${new Date().toISOString().replace(/[:.]/g, '-')}`;
    const outputRoot = path.join(smokeRoot, 'results', runId);
    fs.mkdirSync(outputRoot, { recursive: true });

    const discovery = await runDiscovery({ config: discoveryConfig, queries: queryDocument.queries, outputRoot });
    const threadRuns = [];
    for (let runNumber = 1; runNumber <= protocol.threadGate.runCount; runNumber += 1) {
        threadRuns.push(await runThreads({
            config: threadConfig,
            threads: threadDocument.threads,
            outputRoot,
            runNumber,
        }));
    }

    const replayChecks = threadRuns.flat().filter(item => item.normalized && item.rawArtifact).map(item => {
        const replay = replayThreadArtifact(item.rawArtifact.path);
        return {
            observationId: item.observationId,
            expected: item.normalizedSha256,
            actual: replay.normalizedSha256,
            matches: replay.normalizedSha256 === item.normalizedSha256,
        };
    });
    const discoverySuccessCount = discovery.filter(item => item.candidateCount > 0).length;
    const invalidCandidateCount = discovery.flatMap(item => item.candidates || []).filter(candidate => {
        try {
            const parsed = new URL(candidate.url);
            return parsed.hostname !== 'www.reddit.com' || !/\/comments\/[a-z0-9]+\//i.test(parsed.pathname);
        } catch {
            return true;
        }
    }).length;
    const threadGateResult = evaluateThreadGate({
        threadGate: protocol.threadGate,
        threads: threadDocument.threads,
        runs: threadRuns,
    });
    const threadRunSummaries = threadRuns.map((items, index) => ({
        ...threadGateResult.runs[index],
        successCount: items.filter(item => item.status === 'success').length,
        incompleteCount: items.filter(item => item.status === 'incomplete').length,
        observations: items.map(summarizeObservation),
    }));
    const passed = discoverySuccessCount >= protocol.discoveryGate.minimumQueriesWithCandidate
        && invalidCandidateCount === 0
        && threadGateResult.passed
        && replayChecks.length > 0
        && replayChecks.every(check => check.matches);

    const report = {
        schemaVersion: 2,
        evaluationId: protocol.evaluationId,
        runId,
        sourceCommit,
        startedFromCleanWorktree: true,
        completedAt: new Date().toISOString(),
        fixtureSha256: Object.fromEntries(Object.values(protocol.artifacts).map(relativePath => [relativePath, fileDigest(relativePath)])),
        discovery: {
            passed: discoverySuccessCount >= protocol.discoveryGate.minimumQueriesWithCandidate && invalidCandidateCount === 0,
            queriesWithCandidate: discoverySuccessCount,
            requiredQueriesWithCandidate: protocol.discoveryGate.minimumQueriesWithCandidate,
            invalidCandidateCount,
            observations: discovery.map(summarizeObservation),
        },
        threadFetch: {
            passed: threadGateResult.passed,
            baselineCohort: protocol.threadGate.baselineCohort,
            fixtureExpectations: protocol.threadGate.fixtureExpectations,
            runs: threadRunSummaries,
        },
        replay: {
            passed: replayChecks.length > 0 && replayChecks.every(check => check.matches),
            checks: replayChecks,
        },
        passed,
    };
    const reportPath = path.join(outputRoot, 'report.json');
    fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, { flag: 'wx' });
    process.stdout.write(`${JSON.stringify({
        reportPath,
        passed,
        discovery: report.discovery,
        threadFetch: { passed: report.threadFetch.passed, runs: threadRunSummaries.map(({ observations, ...run }) => run) },
        replay: { passed: report.replay.passed, checkCount: replayChecks.length },
    }, null, 2)}\n`);
    process.exitCode = passed ? 0 : 2;
}

main().catch(error => {
    console.error(error.stack || error.message);
    process.exitCode = 1;
});
