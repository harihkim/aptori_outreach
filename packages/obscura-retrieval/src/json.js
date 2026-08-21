const crypto = require('node:crypto');

function canonicalize(value) {
    if (Array.isArray(value)) return value.map(canonicalize);
    if (value && typeof value === 'object') {
        return Object.fromEntries(
            Object.keys(value).sort().map(key => [key, canonicalize(value[key])]),
        );
    }
    return value;
}

function canonicalJson(value) {
    return JSON.stringify(canonicalize(value));
}

function sha256(value) {
    const input = Buffer.isBuffer(value) ? value : Buffer.from(String(value));
    return crypto.createHash('sha256').update(input).digest('hex');
}

function sha256Json(value) {
    return sha256(canonicalJson(value));
}

module.exports = { canonicalJson, canonicalize, sha256, sha256Json };
