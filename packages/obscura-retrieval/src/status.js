const SENSITIVE_QUERY_KEYS = ['solution', 'js_challenge', 'token', 'jsc_orig_r'];

function redactUrl(value) {
    const parsed = new URL(value);
    for (const key of SENSITIVE_QUERY_KEYS) parsed.searchParams.delete(key);
    return parsed.toString();
}

function redactSensitiveText(value) {
    return String(value).replace(/((?:solution|js_challenge|token|jsc_orig_r)=)[^&\s:]*/gi, '$1<redacted>');
}

function classifyPageAccess({ status, url, title, visibleText }) {
    const text = `${title || ''}\n${visibleText || ''}`.slice(0, 8000);
    const parsed = new URL(url);
    const challengeParams = SENSITIVE_QUERY_KEYS
        .some(key => parsed.searchParams.has(key));

    if (status === 429) return { status: 'rate_limited', reason: 'HTTP 429' };
    if (status === 401) return { status: 'auth_required', reason: 'HTTP 401' };
    if (status === 403) return { status: 'forbidden', reason: 'HTTP 403' };
    if (status === 202 && parsed.hostname.endsWith('duckduckgo.com')) {
        return { status: 'blocked', reason: 'DuckDuckGo challenge response HTTP 202' };
    }
    if (challengeParams) return { status: 'blocked', reason: 'challenge parameters appeared in final URL' };
    if (/unusual traffic|bot challenge|verify (?:you are|that you are) human|duckduckgo.*anomaly|whoa there, pardner|you(?:'ve| have) been blocked/i.test(text)) {
        return { status: 'blocked', reason: 'access challenge detected in rendered page' };
    }
    return null;
}

function classifyError(error) {
    const message = redactSensitiveText(error?.message || error);
    if (/timeout|timed out|network error|ERR_|ECONN|ENOTFOUND|EAI_AGAIN/i.test(message)) {
        return { status: 'upstream_unavailable', reason: message };
    }
    if (/JSON|parse|root post|two-listing array/i.test(message)) {
        return { status: 'parse_failed', reason: message };
    }
    return { status: 'failed', reason: message };
}

module.exports = { classifyError, classifyPageAccess, redactSensitiveText, redactUrl };
