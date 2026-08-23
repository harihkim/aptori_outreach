'use strict';

function assertUnique(values, label) {
    if (new Set(values).size !== values.length) {
        throw new Error(`${label} must not contain duplicates`);
    }
}

function prepareThreadGate(threadGate, threads) {
    const threadIds = threads.map(thread => thread.id);
    assertUnique(threadIds, 'Known-thread corpus ids');

    const baselineIds = threadGate.baselineCohort?.threadIds || [];
    assertUnique(baselineIds, 'Baseline cohort ids');
    if (baselineIds.length === 0) throw new Error('Thread gate requires a baseline cohort');
    if (!Number.isInteger(threadGate.baselineCohort.minimumSuccessfulThreadsPerRun)) {
        throw new Error('Baseline cohort requires an integer success floor');
    }
    if (threadGate.baselineCohort.minimumSuccessfulThreadsPerRun > baselineIds.length) {
        throw new Error('Baseline success floor exceeds its cohort size');
    }

    const unknownBaseline = baselineIds.filter(id => !threadIds.includes(id));
    if (unknownBaseline.length) {
        throw new Error(`Baseline cohort contains unknown fixtures: ${unknownBaseline.join(', ')}`);
    }

    const expectations = new Map();
    for (const expectation of threadGate.fixtureExpectations || []) {
        if (expectations.has(expectation.threadId)) {
            throw new Error(`Duplicate fixture expectation: ${expectation.threadId}`);
        }
        if (!threadIds.includes(expectation.threadId)) {
            throw new Error(`Fixture expectation references unknown fixture: ${expectation.threadId}`);
        }
        if (!Array.isArray(expectation.allowedStatuses) || expectation.allowedStatuses.length === 0) {
            throw new Error(`Fixture expectation has no allowed status: ${expectation.threadId}`);
        }
        expectations.set(expectation.threadId, new Set(expectation.allowedStatuses));
    }

    const uncoveredStressIds = threadIds.filter(
        id => !baselineIds.includes(id) && !expectations.has(id),
    );
    if (uncoveredStressIds.length) {
        throw new Error(`Stress fixtures need explicit expectations: ${uncoveredStressIds.join(', ')}`);
    }

    return { baselineIds: new Set(baselineIds), expectations };
}

function evaluateThreadGate({ threadGate, threads, runs }) {
    const { baselineIds, expectations } = prepareThreadGate(threadGate, threads);
    if (runs.length !== threadGate.runCount) {
        throw new Error(`Expected ${threadGate.runCount} thread runs, received ${runs.length}`);
    }

    const evaluatedRuns = runs.map((observations, index) => {
        if (observations.length !== threads.length) {
            throw new Error(`Thread run ${index + 1} does not match the frozen corpus size`);
        }

        let baselineSuccessCount = 0;
        let invalidTreeCount = 0;
        const expectationMismatches = [];
        const unexpectedFailures = [];

        for (const [itemIndex, observation] of observations.entries()) {
            const threadId = threads[itemIndex].id;
            if (baselineIds.has(threadId) && observation.status === 'success') {
                baselineSuccessCount += 1;
            }
            if (observation.normalized && (
                observation.normalized.validation.duplicateIds.length
                || observation.normalized.validation.missingParentReferences.length
            )) {
                invalidTreeCount += 1;
            }

            const allowedStatuses = expectations.get(threadId);
            if (allowedStatuses && !allowedStatuses.has(observation.status)) {
                expectationMismatches.push({
                    threadId,
                    observedStatus: observation.status,
                    allowedStatuses: [...allowedStatuses],
                });
            }
            if (observation.status !== 'success' && !allowedStatuses?.has(observation.status)) {
                unexpectedFailures.push({ threadId, status: observation.status });
            }
        }

        const passed = (
            baselineSuccessCount >= threadGate.baselineCohort.minimumSuccessfulThreadsPerRun
            && expectationMismatches.length === 0
            && invalidTreeCount === 0
        );
        return {
            runNumber: index + 1,
            passed,
            baselineSuccessCount,
            baselineThreadCount: baselineIds.size,
            requiredBaselineSuccesses: threadGate.baselineCohort.minimumSuccessfulThreadsPerRun,
            expectationMismatches,
            unexpectedFailures,
            invalidTreeCount,
        };
    });

    return {
        passed: evaluatedRuns.every(run => run.passed),
        runs: evaluatedRuns,
    };
}

module.exports = { evaluateThreadGate, prepareThreadGate };
