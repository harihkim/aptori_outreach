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

test('classifies the reported comment counter delta without overclaiming', () => {
    const build = numComments => [
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
                        num_comments: numComments,
                        created_utc: 1_700_000_000,
                        selftext: 'Body',
                        permalink: '/r/example/comments/post/example/',
                    },
                }],
            },
        },
        {
            data: {
                children: [{
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
                        replies: '',
                    },
                }],
            },
        },
    ];
    const withMore = payload => {
        payload[1].data.children.push({
            kind: 'more',
            data: { id: 'more_1', parent_id: 't3_post', count: 5, children: ['u1', 'u2', 'u3', 'u4', 'u5'], depth: 0 },
        });
        return payload;
    };

    assert.equal(normalizeThread(build(1)).validation.counterDeltaClass, 'match');
    assert.equal(normalizeThread(build(4)).validation.counterDeltaClass, 'exceeds_visible_tree');
    assert.equal(normalizeThread(withMore(build(6))).validation.counterDeltaClass, 'within_unresolved_more');
    assert.equal(normalizeThread(build(0)).validation.counterDeltaClass, 'negative_counter_lag');

    const missingCounter = build(1);
    delete missingCounter[0].data.children[0].data.num_comments;
    const result = normalizeThread(missingCounter);
    assert.equal(result.post.totalReportedComments, undefined);
    assert.equal(result.validation.reportedCommentDelta, null);
    assert.equal(result.validation.counterDeltaClass, 'unknown');
});
