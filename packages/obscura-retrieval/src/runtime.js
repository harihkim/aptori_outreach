const { spawn } = require('node:child_process');
const net = require('node:net');

const { chromium } = require('playwright-core');
const { verifyRuntime } = require('./config.js');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function findAvailablePort() {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.unref();
        server.on('error', reject);
        server.listen(0, '127.0.0.1', () => {
            const address = server.address();
            server.close(error => error ? reject(error) : resolve(address.port));
        });
    });
}

async function connectOverCdp(endpoint, processState, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    let lastError;
    while (Date.now() < deadline) {
        if (processState.spawnError) {
            throw new Error(`Obscura failed to spawn: ${processState.spawnError.message}`);
        }
        if (processState.exitCode !== null) {
            throw new Error(`Obscura exited before CDP became ready (exit ${processState.exitCode})`);
        }
        try {
            return await chromium.connectOverCDP(endpoint);
        } catch (error) {
            lastError = error;
            await sleep(200);
        }
    }
    throw new Error(`Obscura CDP startup timed out: ${lastError?.message || 'unknown error'}`);
}

class ObscuraRuntime {
    constructor(config) {
        this.config = config;
        this.browser = null;
        this.context = null;
        this.process = null;
        this.processState = { exitCode: null };
        this.stderr = [];
        this.runtimeIdentity = null;
        this.port = null;
        this.args = null;
    }

    async start() {
        if (this.browser) return this;
        this.runtimeIdentity = verifyRuntime(this.config);
        this.port = await findAvailablePort();
        this.args = [
            'serve',
            '--host', '127.0.0.1',
            '--port', String(this.port),
            '--workers', '1',
            '--max-connections', '1',
            '--quiet',
        ];
        this.process = spawn(this.runtimeIdentity.binaryPath, this.args, {
            stdio: ['ignore', 'ignore', 'pipe'],
        });
        this.process.stderr.on('data', chunk => {
            const remaining = Math.max(0, 65536 - this.stderr.join('').length);
            if (remaining) this.stderr.push(chunk.toString().slice(0, remaining));
        });
        this.process.on('error', error => {
            this.processState.exitCode = 1;
            this.processState.spawnError = error;
        });
        this.process.on('exit', code => { this.processState.exitCode = code; });

        try {
            this.browser = await connectOverCdp(
                `http://127.0.0.1:${this.port}`,
                this.processState,
                this.config.obscura.startupTimeoutMs,
            );
            this.context = this.browser.contexts()[0] || await this.browser.newContext();
            return this;
        } catch (error) {
            await this.stop();
            throw error;
        }
    }

    async runPage(targetUrl, handler) {
        if (!this.browser) await this.start();
        await this.context.clearCookies();
        const page = await this.context.newPage();
        const network = {
            requests: 0,
            responses: 0,
            failedRequests: 0,
            transferredResponseBytes: 0,
        };
        page.on('request', () => { network.requests += 1; });
        page.on('requestfailed', () => { network.failedRequests += 1; });
        page.on('response', async response => {
            network.responses += 1;
            const header = await response.headerValue('content-length').catch(() => null);
            if (header && /^\d+$/.test(header)) network.transferredResponseBytes += Number(header);
        });

        try {
            const navigationResponse = await page.goto(targetUrl, {
                waitUntil: 'load',
                timeout: this.config.obscura.navigationTimeoutMs,
            });
            return await handler({ page, navigationResponse, network });
        } finally {
            await page.close().catch(() => {});
        }
    }

    describe() {
        return {
            ...this.runtimeIdentity,
            obscuraArguments: this.args,
            host: '127.0.0.1',
            port: this.port,
        };
    }

    async stop() {
        if (this.browser) await this.browser.close().catch(() => {});
        this.browser = null;
        this.context = null;
        if (this.process && this.process.exitCode === null) {
            this.process.kill('SIGTERM');
            await Promise.race([
                new Promise(resolve => this.process.once('exit', resolve)),
                sleep(2000),
            ]);
            if (this.process.exitCode === null) {
                this.process.kill('SIGKILL');
                await Promise.race([
                    new Promise(resolve => this.process.once('exit', resolve)),
                    sleep(1000),
                ]);
            }
        }
        this.process = null;
    }
}

module.exports = { ObscuraRuntime, findAvailablePort };
