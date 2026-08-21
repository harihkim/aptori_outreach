const { sha256Json } = require('./json.js');

const REDDIT_HOSTS = new Set(['reddit.com', 'www.reddit.com', 'old.reddit.com']);
const THREAD_PATH = /^\/(?:r\/([^/]+)\/)?comments\/([a-z0-9]+)(?:\/([^/?#]+))?\/?$/i;

function unwrapDuckDuckGoUrl(value) {
    const parsed = new URL(value, 'https://lite.duckduckgo.com');
    if (parsed.hostname === 'duckduckgo.com' || parsed.hostname.endsWith('.duckduckgo.com')) {
        const unwrapped = parsed.searchParams.get('uddg');
        if (!unwrapped) throw new Error('DuckDuckGo result did not contain an uddg target');
        return unwrapped;
    }
    return parsed.toString();
}

function canonicalizeRedditThreadUrl(value) {
    const unwrapped = unwrapDuckDuckGoUrl(value);
    const parsed = new URL(unwrapped);
    if (!REDDIT_HOSTS.has(parsed.hostname.toLowerCase())) {
        throw new Error(`Unsupported Reddit host: ${parsed.hostname}`);
    }

    const normalizedPath = parsed.pathname.replace(/\.json\/?$/i, '');
    const match = normalizedPath.match(THREAD_PATH);
    if (!match) throw new Error(`Not a Reddit thread URL: ${parsed.pathname}`);

    const subreddit = match[1] || null;
    const postId = match[2].toLowerCase();
    const slug = match[3] || '_';
    const prefix = subreddit ? `/r/${subreddit}` : '';
    return {
        url: `https://www.reddit.com${prefix}/comments/${postId}/${slug}/`,
        postId,
        externalSourceId: `t3_${postId}`,
        subreddit,
    };
}

function redditJsonUrl(value, { commentLimit = 500, sort = 'confidence' } = {}) {
    const canonical = canonicalizeRedditThreadUrl(value);
    const parsed = new URL(canonical.url);
    parsed.pathname = `${parsed.pathname.replace(/\/$/, '')}.json`;
    parsed.searchParams.set('limit', String(commentLimit));
    parsed.searchParams.set('raw_json', '1');
    parsed.searchParams.set('sort', sort);
    return parsed.toString();
}

function normalizeDiscoveryRows(rows, { limit = 50 } = {}) {
    const candidates = [];
    const seen = new Set();

    for (const row of rows) {
        let canonical;
        try {
            canonical = canonicalizeRedditThreadUrl(row.href);
        } catch {
            continue;
        }
        if (seen.has(canonical.externalSourceId)) continue;
        seen.add(canonical.externalSourceId);
        candidates.push({
            rank: candidates.length + 1,
            url: canonical.url,
            externalSourceId: canonical.externalSourceId,
            subreddit: canonical.subreddit,
            title: String(row.title || '').trim(),
            snippet: String(row.snippet || '').replace(/\s+/g, ' ').trim(),
            displayedUrl: String(row.displayedUrl || '').trim() || null,
        });
        if (candidates.length >= limit) break;
    }

    return candidates;
}

function normalizeThread(payload) {
    if (!Array.isArray(payload)) throw new Error('Reddit response must be a two-listing array');
    const postObj = payload[0]?.data?.children?.[0]?.data;
    if (!postObj?.id) throw new Error('Reddit response did not contain a root post');

    const post = {
        id: postObj.name || `t3_${postObj.id}`,
        postId: postObj.id,
        title: postObj.title || '',
        author: postObj.author || null,
        score: Number.isFinite(postObj.score) ? postObj.score : null,
        upvoteRatio: Number.isFinite(postObj.upvote_ratio) ? postObj.upvote_ratio : null,
        subreddit: postObj.subreddit_name_prefixed || null,
        totalReportedComments: Number.isFinite(postObj.num_comments) ? postObj.num_comments : null,
        createdUtc: postObj.created_utc || null,
        createdIso: postObj.created_utc ? new Date(postObj.created_utc * 1000).toISOString() : null,
        selftext: postObj.selftext || '',
        permalink: postObj.permalink || null,
        postType: postObj.is_self ? 'self' : postObj.is_video ? 'video' : 'link_or_media',
        locked: Boolean(postObj.locked),
    };

    const comments = [];
    const unresolvedMore = [];

    function parseChildren(children, traversalDepth = 0) {
        if (!Array.isArray(children)) return;
        for (const child of children) {
            const item = child?.data;
            if (child?.kind === 't1' && item?.id) {
                comments.push({
                    id: item.name || `t1_${item.id}`,
                    commentId: item.id,
                    author: item.author || null,
                    score: Number.isFinite(item.score) ? item.score : null,
                    depth: Number.isInteger(item.depth) ? item.depth : traversalDepth,
                    parentId: item.parent_id || null,
                    createdUtc: item.created_utc || null,
                    createdIso: item.created_utc ? new Date(item.created_utc * 1000).toISOString() : null,
                    body: item.body || '',
                    visibility: item.author === '[deleted]' || item.body === '[deleted]'
                        ? 'deleted'
                        : item.body === '[removed]' ? 'removed' : 'visible',
                });
                parseChildren(item.replies?.data?.children, traversalDepth + 1);
            } else if (child?.kind === 'more' && item) {
                unresolvedMore.push({
                    id: item.id || null,
                    parentId: item.parent_id || null,
                    count: Number.isFinite(item.count) ? item.count : 0,
                    childIds: Array.isArray(item.children) ? item.children : [],
                    depth: Number.isInteger(item.depth) ? item.depth : traversalDepth,
                });
            }
        }
    }

    parseChildren(payload[1]?.data?.children || []);

    const ids = comments.map(comment => comment.id);
    const idSet = new Set(ids);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    const missingParentReferences = comments
        .filter(comment => comment.parentId !== post.id && !idSet.has(comment.parentId))
        .map(comment => ({ id: comment.id, parentId: comment.parentId }));

    const unresolvedMoreChildCount = unresolvedMore.reduce((sum, item) => sum + item.childIds.length, 0);
    const reportedCommentDelta = post.totalReportedComments === null
        ? null
        : post.totalReportedComments - comments.length;
    const counterDeltaClass = reportedCommentDelta === null
        ? 'unknown'
        : reportedCommentDelta === 0
            ? 'match'
            : reportedCommentDelta > 0 && unresolvedMoreChildCount >= reportedCommentDelta
                ? 'within_unresolved_more'
                : reportedCommentDelta > 0
                    ? 'exceeds_visible_tree'
                    : 'negative_counter_lag';

    const normalized = {
        post,
        comments,
        unresolvedMore,
        validation: {
            extractedCommentCount: comments.length,
            uniqueCommentCount: idSet.size,
            duplicateIds,
            missingParentReferences,
            maxDepth: comments.length ? Math.max(...comments.map(comment => comment.depth)) : null,
            unresolvedMoreNodeCount: unresolvedMore.length,
            unresolvedMoreChildCount,
            sourceTreeExhausted: unresolvedMore.length === 0,
            reportedCommentDelta,
            counterDeltaClass,
        },
    };

    normalized.normalizedSha256 = sha256Json(normalized);
    normalized.normalizedContentSha256 = sha256Json({
        post: {
            id: post.id,
            title: post.title,
            author: post.author,
            createdUtc: post.createdUtc,
            selftext: post.selftext,
            permalink: post.permalink,
        },
        comments: comments.map(comment => ({
            id: comment.id,
            author: comment.author,
            depth: comment.depth,
            parentId: comment.parentId,
            createdUtc: comment.createdUtc,
            body: comment.body,
            visibility: comment.visibility,
        })),
        unresolvedMore,
    });
    return normalized;
}

module.exports = {
    canonicalizeRedditThreadUrl,
    normalizeDiscoveryRows,
    normalizeThread,
    redditJsonUrl,
    unwrapDuckDuckGoUrl,
};
