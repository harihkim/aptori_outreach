const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const { sha256 } = require('./json.js');

function safeName(value) {
    return String(value).replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-|-$/g, '').slice(0, 80) || 'attempt';
}

function createAttempt(outputRoot, capability, logicalId) {
    const attemptId = `${new Date().toISOString().replace(/[:.]/g, '-')}_${crypto.randomBytes(4).toString('hex')}`;
    const parent = path.resolve(outputRoot, safeName(capability));
    fs.mkdirSync(parent, { recursive: true });
    const directory = path.join(parent, `${safeName(logicalId)}_${attemptId}`);
    fs.mkdirSync(directory, { recursive: false });
    return { attemptId, directory };
}

function writeRawArtifact(attempt, filename, content) {
    const buffer = Buffer.isBuffer(content) ? content : Buffer.from(String(content));
    const artifactPath = path.join(attempt.directory, filename);
    fs.writeFileSync(artifactPath, buffer, { flag: 'wx' });
    return {
        path: artifactPath,
        filename,
        bytes: buffer.byteLength,
        sha256: sha256(buffer),
    };
}

function writeObservation(attempt, observation) {
    const observationPath = path.join(attempt.directory, 'observation.json');
    fs.writeFileSync(observationPath, `${JSON.stringify(observation, null, 2)}\n`, { flag: 'wx' });
    return observationPath;
}

module.exports = { createAttempt, writeObservation, writeRawArtifact };
