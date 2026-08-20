const assert = require('node:assert/strict');
const test = require('node:test');

const {
    canonicalJsonUrl,
    normalizeThread,
    redactSensitiveText,
    redactUrl,
} = require('./obscura_deep_comment_extractor.js');

test('builds a canonical Reddit JSON URL without carrying input query data', () => {
    assert.equal(
        canonicalJsonUrl('https://reddit.com/r/example/comments/abc/title/?context=3#fragment'),
        'https://www.reddit.com/r/example/comments/abc/title.json?limit=500&raw_json=1&sort=confidence',
    );
    assert.throws(
        () => canonicalJsonUrl('https://example.com/r/example/comments/abc/title/'),
        /Unsupported target host/,
    );
});

test('redacts challenge parameters in URLs and captured logs', () => {
    const input = 'https://www.reddit.com/x?solution=abc&js_challenge=1&token=secret&jsc_orig_r=&keep=yes';
    assert.equal(redactUrl(input), 'https://www.reddit.com/x?keep=yes');

    const log = redactSensitiveText(`at ${input}:3:20`);
    assert.doesNotMatch(log, /abc|secret/);
    assert.match(log, /solution=<redacted>/);
    assert.match(log, /keep=yes/);
});

test('normalizes visible and deleted comments while preserving unresolved more nodes', () => {
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
    assert.equal(result.comments.length, 2);
    assert.equal(result.comments[1].visibility, 'deleted');
    assert.equal(result.validation.maxDepth, 1);
    assert.equal(result.validation.unresolvedMoreNodeCount, 1);
    assert.equal(result.validation.unresolvedMoreChildCount, 1);
    assert.equal(result.validation.sourceTreeExhausted, false);
    assert.deepEqual(result.validation.duplicateIds, []);
    assert.deepEqual(result.validation.missingParentReferences, []);
});
