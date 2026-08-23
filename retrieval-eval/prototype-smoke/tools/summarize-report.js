#!/usr/bin/env node
// Summarizes a prototype smoke report.json into one TSV line for the daily log.
//
// Usage: node summarize-report.js <path-to-report.json>
//
// Columns:
//   timestamp  evaluationId  runId  passed  discoveryWithCandidate(required)
//   invalidCandidates  run1BaselineSuccess(total)  run2BaselineSuccess(total)
//   replayMatches(checks)  unexpectedFailures(JSON)  failureHistogram(JSON)
//
// unexpectedFailures lists thread fixtures whose outcome was not "success" and
// is not listed in protocol.json threadGate.expectedNonSuccessThreadIds. An
// empty array means every non-success was expected fixture behavior; any entry
// is a regression signal worth investigating the same day.

const fs = require('node:fs');
const path = require('node:path');

function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function postIdFromUrl(url) {
    const match = String(url).match(/\/comments\/([a-z0-9]+)\//i);
    return match ? match[1].toLowerCase() : null;
}

function main() {
    const reportPath = process.argv[2];
    if (!reportPath) {
        console.error('usage: node summarize-report.js <path-to-report.json>');
        process.exitCode = 1;
        return;
    }
    const report = readJson(reportPath);
    const smokeRoot = path.resolve(__dirname, '..');

    let expectedNonSuccess = [];
    try {
        const historicalProtocol = report.schemaVersion >= 2 ? 'protocol.json' : 'protocol-v2.json';
        const protocol = readJson(path.join(smokeRoot, historicalProtocol));
        expectedNonSuccess = protocol.threadGate.expectedNonSuccessThreadIds || [];
    } catch {
        // Protocol unreadable: every non-success will be reported as unexpected.
    }

    let threadIdByPostId = new Map();
    try {
        const corpus = readJson(path.join(smokeRoot, 'known-threads-2026-08.json'));
        threadIdByPostId = new Map(corpus.threads
            .map(thread => [postIdFromUrl(thread.url), thread.id])
            .filter(([postId]) => Boolean(postId)));
    } catch {
        // Corpus unreadable: fall back to raw external source IDs below.
    }

    const histogram = {};
    for (const observation of [
        ...report.discovery.observations,
        ...report.threadFetch.runs.flatMap(run => run.observations),
    ]) {
        if (observation.status === 'success') continue;
        histogram[observation.status || 'unknown'] = (histogram[observation.status || 'unknown'] || 0) + 1;
    }

    const firstObservationBySource = new Map();
    for (const run of report.threadFetch.runs) {
        for (const observation of run.observations) {
            if (!firstObservationBySource.has(observation.externalSourceId)) {
                firstObservationBySource.set(observation.externalSourceId, observation);
            }
        }
    }
    const unexpected = [];
    if (report.schemaVersion >= 2) {
        const unique = new Set(report.threadFetch.runs.flatMap(run => (
            run.unexpectedFailures || []
        )).map(failure => `${failure.threadId} (${failure.status})`));
        unexpected.push(...unique);
    } else {
        for (const [externalSourceId, observation] of firstObservationBySource) {
            if (observation.status === 'success') continue;
            const threadId = threadIdByPostId.get(externalSourceId.replace(/^t3_/, '')) || externalSourceId;
            if (!expectedNonSuccess.includes(threadId)) {
                unexpected.push(`${threadId} (${observation.status})`);
            }
        }
    }

    const runs = report.threadFetch.runs.map(run => {
        const total = Array.isArray(run.observations) ? run.observations.length : 0;
        const successes = Number.isFinite(run.baselineSuccessCount)
            ? run.baselineSuccessCount
            : Array.isArray(run.observations)
                ? run.observations.filter(observation => observation.status === 'success').length
                : Number.isFinite(run.successCount) ? run.successCount : 0;
        const denominator = Number.isFinite(run.baselineThreadCount) ? run.baselineThreadCount : total;
        return `${successes}(${denominator})`;
    });
    const replayMatches = report.replay.checks.filter(check => check.matches).length;
    const row = [
        new Date().toISOString(),
        report.evaluationId,
        report.runId,
        report.passed ? 1 : 0,
        `${report.discovery.queriesWithCandidate}(${report.discovery.requiredQueriesWithCandidate})`,
        report.discovery.invalidCandidateCount,
        runs[0] || '0(0)',
        runs[1] || '0(0)',
        `${replayMatches}(${report.replay.checks.length})`,
        JSON.stringify(unexpected),
        JSON.stringify(histogram),
    ];
    process.stdout.write(row.join('\t') + '\n');
}

main();
