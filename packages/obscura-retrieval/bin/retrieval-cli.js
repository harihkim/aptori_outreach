#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

const {
    ObscuraDuckDuckGoLiteDiscoverySource,
    ObscuraRedditThreadFetcher,
    ObscuraRuntime,
    readProviderConfig,
} = require('../src/index.js');

function parseArgs(argv) {
    const [command, ...rest] = argv;
    const values = { command };
    for (let index = 0; index < rest.length; index += 2) {
        const key = rest[index];
        const value = rest[index + 1];
        if (!key?.startsWith('--') || value === undefined) throw new Error(`Invalid argument near ${key || '<end>'}`);
        values[key.slice(2)] = value;
    }
    for (const required of ['config', 'input', 'output-root']) {
        if (!values[required]) throw new Error(`Missing --${required}`);
    }
    if (!['discover', 'fetch-thread'].includes(command)) throw new Error(`Unknown command: ${command}`);
    return values;
}

async function main() {
    const args = parseArgs(process.argv.slice(2));
    const expectedCapability = args.command === 'discover' ? 'discovery' : 'thread_fetch';
    const config = readProviderConfig(path.resolve(args.config), { requiredCapability: expectedCapability });
    const inputDocument = JSON.parse(fs.readFileSync(path.resolve(args.input), 'utf8'));
    const collection = inputDocument.queries || inputDocument.threads;
    const input = Array.isArray(collection)
        ? collection.find(item => item.id === args.id)
        : inputDocument;
    if (!input) throw new Error(`Input id not found: ${args.id || '<missing --id>'}`);
    const runtime = new ObscuraRuntime(config);
    await runtime.start();
    try {
        const adapter = args.command === 'discover'
            ? new ObscuraDuckDuckGoLiteDiscoverySource({ config, runtime, outputRoot: args['output-root'] })
            : new ObscuraRedditThreadFetcher({ config, runtime, outputRoot: args['output-root'] });
        const observation = args.command === 'discover'
            ? await adapter.discover(input)
            : await adapter.fetchThread(input);
        process.stdout.write(`${JSON.stringify({
            observationId: observation.observationId,
            capability: observation.capability,
            status: observation.status,
            failureReason: observation.failureReason,
            candidateCount: observation.candidateCount,
            candidates: observation.candidates,
            externalSourceId: observation.externalSourceId,
            normalizedSha256: observation.normalizedSha256,
            normalizedContentSha256: observation.normalizedContentSha256,
            validation: observation.normalized?.validation,
            evidenceDirectory: observation.evidenceDirectory,
        }, null, 2)}\n`);
        process.exitCode = ['success', 'incomplete', 'no_results'].includes(observation.status) ? 0 : 2;
    } finally {
        await runtime.stop();
    }
}

main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
});
