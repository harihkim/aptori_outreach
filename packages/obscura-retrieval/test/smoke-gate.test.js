const assert = require('node:assert/strict');
const test = require('node:test');

const { evaluateThreadGate, prepareThreadGate } = require('../src/smoke-gate.js');

const threads = [
    { id: 'baseline-1' },
    { id: 'baseline-2' },
    { id: 'baseline-3' },
    { id: 'stress-incomplete' },
    { id: 'stress-boundary' },
];

const threadGate = {
    runCount: 2,
    baselineCohort: {
        threadIds: ['baseline-1', 'baseline-2', 'baseline-3'],
        minimumSuccessfulThreadsPerRun: 2,
    },
    fixtureExpectations: [
        { threadId: 'stress-incomplete', allowedStatuses: ['incomplete'] },
        { threadId: 'stress-boundary', allowedStatuses: ['incomplete', 'success'] },
    ],
};

function observation(status, valid = true) {
    return {
        status,
        normalized: status === 'success' || status === 'incomplete'
            ? { validation: {
                duplicateIds: valid ? [] : ['duplicate'],
                missingParentReferences: [],
            } }
            : null,
    };
}

test('stratified gate preserves the baseline ratio without counting stress fixtures', () => {
    const run = [
        observation('success'),
        observation('success'),
        observation('blocked'),
        observation('incomplete'),
        observation('success'),
    ];

    const result = evaluateThreadGate({ threadGate, threads, runs: [run, run] });

    assert.equal(result.passed, true);
    assert.equal(result.runs[0].baselineSuccessCount, 2);
    assert.equal(result.runs[0].baselineThreadCount, 3);
    assert.deepEqual(result.runs[0].expectationMismatches, []);
});

test('stress outcome mismatch fails even when the baseline passes', () => {
    const run = [
        observation('success'),
        observation('success'),
        observation('success'),
        observation('parse_failed'),
        observation('success'),
    ];

    const result = evaluateThreadGate({ threadGate, threads, runs: [run, run] });

    assert.equal(result.passed, false);
    assert.deepEqual(result.runs[0].expectationMismatches, [{
        threadId: 'stress-incomplete',
        observedStatus: 'parse_failed',
        allowedStatuses: ['incomplete'],
    }]);
});

test('tree corruption overrides otherwise acceptable outcomes', () => {
    const run = [
        observation('success', false),
        observation('success'),
        observation('success'),
        observation('incomplete'),
        observation('success'),
    ];

    const result = evaluateThreadGate({ threadGate, threads, runs: [run, run] });

    assert.equal(result.passed, false);
    assert.equal(result.runs[0].invalidTreeCount, 1);
});

test('protocol rejects stress fixtures without explicit expectations', () => {
    assert.throws(
        () => prepareThreadGate({ ...threadGate, fixtureExpectations: [] }, threads),
        /Stress fixtures need explicit expectations/,
    );
});
