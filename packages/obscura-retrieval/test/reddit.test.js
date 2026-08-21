const assert = require('node:assert/strict');
const test = require('node:test');

const {
    canonicalizeRedditThreadUrl,
    normalizeDiscoveryRows,
    normalizeThread,
    redditJsonUrl,
} = require('../src/reddit.js');

test('unwraps and canonicalizes DuckDuckGo Reddit thread URLs', () => {
    const wrapped = 'https://duckduckgo.com/l/?uddg=https%3A%2F%2Fold.reddit.com%2Fr%2Fcybersecurity%2Fcomments%2Fabc123%2Ftitle%2F&rut=ignored';
    assert.deepEqual(canonicalizeRedditThreadUrl(wrapped), {
        url: 'https://www.reddit.com/r/cybersecurity/comments/abc123/title/',
        postId: 'abc123',
        externalSourceId: 't3_abc123',
        subreddit: 'cybersecurity',
    });
    assert.throws(
        () => canonicalizeRedditThreadUrl('https://example.com/r/test/comments/abc/title/'),
        /Unsupported Reddit host/,
    );
    assert.throws(
        () => canonicalizeRedditThreadUrl('https://www.reddit.com/r/test/'),
        /Not a Reddit thread URL/,
    );
});

test('builds the fixed in-origin JSON endpoint without input query parameters', () => {
    assert.equal(
        redditJsonUrl('https://reddit.com/r/example/comments/abc/title/?context=3#fragment'),
        'https://www.reddit.com/r/example/comments/abc/title.json?limit=500&raw_json=1&sort=confidence',
    );
    assert.equal(
        redditJsonUrl('https://www.reddit.com/r/example/comments/abc/title.json?raw_json=0'),
        'https://www.reddit.com/r/example/comments/abc/title.json?limit=500&raw_json=1&sort=confidence',
    );
});

test('normalizes only valid canonical Reddit threads and deduplicates by source ID', () => {
    const rows = [
        {
            href: '//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reddit.com%2Fr%2Fnetsec%2Fcomments%2Fabc123%2Fone%2F',
            title: ' First result ',
            snippet: '  useful   text ',
        },
        {
            href: 'https://www.reddit.com/r/netsec/comments/abc123/duplicate/',
            title: 'Duplicate',
        },
        {
            href: 'https://www.reddit.com/r/netsec/',
            title: 'Not a thread',
        },
    ];
    assert.deepEqual(normalizeDiscoveryRows(rows), [{
        rank: 1,
        url: 'https://www.reddit.com/r/netsec/comments/abc123/one/',
        externalSourceId: 't3_abc123',
        subreddit: 'netsec',
        title: 'First result',
        snippet: 'useful text',
        displayedUrl: null,
    }]);
});

test('normalizes the comment tree and marks unresolved more nodes incomplete', () => {
    const payload = [
        {
            data: {
                children: [{
                    kind: 't3',
                    data: {
                        id: 'post',
                        name: 't3_post',
                        title: 'Example',
                        author: 'op',
                        score: 5,
                        upvote_ratio: 0.9,
                        subreddit_name_prefixed: 'r/example',
                        num_comments: 3,
                        created_utc: 1_700_000_000,
                        selftext: 'Body',
                        permalink: '/r/example/comments/post/example/',
                        is_self: true,
                        locked: false,
                    },
                }],
            },
        },
        {
            data: {
                children: [
                    {
                        kind: 't1',
                        data: {
                            id: 'visible',
                            name: 't1_visible',
                            author: 'person',
                            score: 2,
                            depth: 0,
                            parent_id: 't3_post',
                            created_utc: 1_700_000_001,
                            body: 'Visible reply',
                            replies: {
                                data: {
                                    children: [{
                                        kind: 't1',
                                        data: {
                                            id: 'deleted',
                                            name: 't1_deleted',
                                            author: '[deleted]',
                                            score: 0,
                                            depth: 1,
                                            parent_id: 't1_visible',
                                            created_utc: 1_700_000_002,
                                            body: '[deleted]',
                                            replies: '',
                                        },
                                    }],
                                },
                            },
                        },
                    },
                    {
                        kind: 'more',
                        data: {
                            id: 'more_1',
                            parent_id: 't3_post',
                            count: 1,
                            children: ['unresolved'],
                            depth: 0,
                        },
                    },
                ],
            },
        },
    ];

    const result = normalizeThread(payload);
    assert.equal(result.post.postType, 'self');
    assert.equal(result.comments.length, 2);
    assert.equal(result.comments[1].visibility, 'deleted');
    assert.equal(result.validation.maxDepth, 1);
    assert.equal(result.validation.unresolvedMoreNodeCount, 1);
    assert.equal(result.validation.sourceTreeExhausted, false);
    assert.deepEqual(result.validation.duplicateIds, []);
    assert.deepEqual(result.validation.missingParentReferences, []);
    assert.match(result.normalizedSha256, /^[a-f0-9]{64}$/);
    assert.match(result.normalizedContentSha256, /^[a-f0-9]{64}$/);
});

test('content hash ignores volatile scores but full normalized hash does not', () => {
    const base = [
        { data: { children: [{ kind: 't3', data: { id: 'p', name: 't3_p', title: 'T', author: 'a', score: 1, upvote_ratio: 1, subreddit_name_prefixed: 'r/x', num_comments: 1, created_utc: 1, selftext: 'B', permalink: '/r/x/comments/p/t/', is_self: true } }] } },
        { data: { children: [{ kind: 't1', data: { id: 'c', name: 't1_c', author: 'b', score: 1, depth: 0, parent_id: 't3_p', created_utc: 2, body: 'C', replies: '' } }] } },
    ];
    const changed = structuredClone(base);
    changed[0].data.children[0].data.score = 99;
    changed[1].data.children[0].data.score = 88;
    const first = normalizeThread(base);
    const second = normalizeThread(changed);
    assert.notEqual(first.normalizedSha256, second.normalizedSha256);
    assert.equal(first.normalizedContentSha256, second.normalizedContentSha256);
});
