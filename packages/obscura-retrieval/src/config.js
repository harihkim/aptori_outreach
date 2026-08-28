const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { sha256, sha256Json } = require('./json.js');

function readProviderConfig(configPath, { requiredCapability = null } = {}) {
    const absolutePath = path.resolve(configPath);
    const raw = fs.readFileSync(absolutePath, 'utf8');
    const config = JSON.parse(raw);
    validateConfigShape(config);
    if (requiredCapability !== null && config.capability !== requiredCapability) {
        throw new Error(`Provider config capability mismatch: expected ${requiredCapability}, got ${config.capability}`);
    }
    return {
        ...config,
        configPath: absolutePath,
        configSha256: sha256(raw),
    };
}

function validateConfigShape(config) {
    if (config?.schemaVersion !== 1) throw new Error('Provider config schemaVersion must be 1');
    if (!config.providerVariant) throw new Error('Provider config requires providerVariant');
    if (!['discovery', 'thread_fetch'].includes(config.capability)) {
        throw new Error('Provider config capability must be discovery or thread_fetch');
    }
    if (config.accessMode !== 'obscura_cdp_standard_anonymous') {
        throw new Error('Only obscura_cdp_standard_anonymous is authorized');
    }
    if (config.obscura?.stealth !== false) throw new Error('Obscura stealth must be false');
    if (config.obscura?.proxy !== null) throw new Error('Obscura proxy must be null');
    if (config.obscura?.storageDir !== null) throw new Error('Persistent Obscura storage is not authorized');
    if (config.obscura?.workers !== 1 || config.obscura?.maxConnections !== 1) {
        throw new Error('Obscura workers and maxConnections must both be 1');
    }
    if (!config.obscura?.version || !config.obscura?.binarySha256 || !config.obscura?.binaryPath) {
        throw new Error('Pinned Obscura version, binaryPath, and binarySha256 are required');
    }
    if (!config.runtime?.nodeVersion || !config.runtime?.playwrightCoreVersion || config.runtime?.environment !== 'WSL') {
        throw new Error('Pinned WSL, Node, and Playwright Core runtime values are required');
    }
    if (config.capability === 'discovery') {
        if (!config.discovery
            || typeof config.discovery.minimumGapMs !== 'number'
            || typeof config.discovery.maxCandidates !== 'number') {
            throw new Error('Provider config discovery capability requires discovery.minimumGapMs and discovery.maxCandidates');
        }
        if (config.thread != null) {
            throw new Error('Provider config discovery capability must not define thread settings');
        }
    } else {
        if (!config.thread
            || typeof config.thread.minimumGapMs !== 'number'
            || typeof config.thread.commentLimit !== 'number'
            || typeof config.thread.sort !== 'string') {
            throw new Error('Provider config thread_fetch capability requires thread.minimumGapMs, thread.commentLimit, and thread.sort');
        }
        if (config.discovery != null) {
            throw new Error('Provider config thread_fetch capability must not define discovery settings');
        }
    }
    return config;
}

function verifyRuntime(config) {
    const binaryPath = process.env.OBSCURA_BIN || config.obscura.binaryPath;
    fs.accessSync(binaryPath, fs.constants.X_OK);
    const binarySha256 = sha256(fs.readFileSync(binaryPath));
    if (binarySha256 !== config.obscura.binarySha256) {
        throw new Error(`Obscura binary hash drift: expected ${config.obscura.binarySha256}, got ${binarySha256}`);
    }

    const versionOutput = execFileSync(binaryPath, ['--version'], { encoding: 'utf8', timeout: 5000 }).trim();
    if (versionOutput !== `obscura ${config.obscura.version}`) {
        throw new Error(`Obscura version drift: expected obscura ${config.obscura.version}, got ${versionOutput}`);
    }
    if (process.version !== config.runtime.nodeVersion) {
        throw new Error(`Node version drift: expected ${config.runtime.nodeVersion}, got ${process.version}`);
    }
    const playwrightCoreVersion = require('playwright-core/package.json').version;
    if (playwrightCoreVersion !== config.runtime.playwrightCoreVersion) {
        throw new Error(`Playwright Core version drift: expected ${config.runtime.playwrightCoreVersion}, got ${playwrightCoreVersion}`);
    }
    if (!/microsoft/i.test(os.release()) && !process.env.WSL_DISTRO_NAME) {
        throw new Error('ADR-012 reference runtime requires WSL');
    }

    return {
        binaryPath,
        binarySha256,
        obscuraVersion: config.obscura.version,
        nodeVersion: process.version,
        playwrightCoreVersion,
        wslDistro: process.env.WSL_DISTRO_NAME || null,
        kernel: os.release(),
        runtimeIdentitySha256: sha256Json({
            binarySha256,
            obscuraVersion: config.obscura.version,
            nodeVersion: process.version,
            playwrightCoreVersion,
            kernel: os.release(),
        }),
    };
}

module.exports = { readProviderConfig, validateConfigShape, verifyRuntime };
