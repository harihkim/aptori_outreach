"""Golden vectors for deterministic post-commit thread normalization."""

from copy import deepcopy
from typing import Any

from app.conversations.normalizer import normalize_reddit_thread


def thread_payload(*, include_more: bool = True) -> list[Any]:
    children: list[Any] = [
        {
            "kind": "t1",
            "data": {
                "id": "visible",
                "name": "t1_visible",
                "author": "person",
                "score": 2,
                "depth": 0,
                "parent_id": "t3_post",
                "created_utc": 1_700_000_001,
                "body": "Visible reply",
                "replies": {
                    "data": {
                        "children": [
                            {
                                "kind": "t1",
                                "data": {
                                    "id": "deleted",
                                    "name": "t1_deleted",
                                    "author": "[deleted]",
                                    "score": 0,
                                    "depth": 1,
                                    "parent_id": "t1_visible",
                                    "created_utc": 1_700_000_002,
                                    "body": "[deleted]",
                                    "replies": "",
                                },
                            }
                        ]
                    }
                },
            },
        }
    ]
    if include_more:
        children.append(
            {
                "kind": "more",
                "data": {
                    "id": "more_1",
                    "parent_id": "t3_post",
                    "count": 1,
                    "children": ["unresolved"],
                    "depth": 0,
                },
            }
        )
    return [
        {
            "data": {
                "children": [
                    {
                        "kind": "t3",
                        "data": {
                            "id": "post",
                            "name": "t3_post",
                            "title": "Example",
                            "author": "op",
                            "score": 5,
                            "upvote_ratio": 0.9,
                            "subreddit_name_prefixed": "r/example",
                            "num_comments": 3,
                            "created_utc": 1_700_000_000,
                            "selftext": "Body",
                            "permalink": "/r/example/comments/post/example/",
                            "is_self": True,
                            "locked": False,
                        },
                    }
                ]
            }
        },
        {"data": {"children": children}},
    ]


def test_incomplete_golden_vector_matches_frozen_node_runtime() -> None:
    result = normalize_reddit_thread(thread_payload())

    assert result.source_tree_exhausted is False
    assert result.root_external_source_id == "t3_post"
    assert result.normalized_sha256 == (
        "0bb8007228cbeae0f785a7ba10a54141bdb12aae68c4cd9464ce26def52f6833"
    )
    assert result.normalized_content_sha256 == (
        "a5131ccc958a17f6bad0819b1e823276019adcf35a7092103c82469e187514b7"
    )
    validation = result.content["validation"]
    assert isinstance(validation, dict)
    assert validation["sourceTreeExhausted"] is False
    assert validation["unresolvedMoreNodeCount"] == 1


def test_content_identity_ignores_volatile_scores() -> None:
    changed = deepcopy(thread_payload())
    post = changed[0]["data"]["children"][0]["data"]
    comment = changed[1]["data"]["children"][0]["data"]
    post["score"] = 99
    comment["score"] = 88

    first = normalize_reddit_thread(thread_payload())
    second = normalize_reddit_thread(changed)

    assert first.normalized_sha256 != second.normalized_sha256
    assert first.normalized_content_sha256 == second.normalized_content_sha256


def test_integer_valued_floats_match_json_stringify_number_rendering() -> None:
    float_payload = deepcopy(thread_payload())
    post = float_payload[0]["data"]["children"][0]["data"]
    comment = float_payload[1]["data"]["children"][0]["data"]
    post["score"] = 5.0
    post["upvote_ratio"] = 1.0
    post["created_utc"] = 1_700_000_000.0
    comment["score"] = 2.0

    integer_payload = deepcopy(float_payload)
    integer_post = integer_payload[0]["data"]["children"][0]["data"]
    integer_comment = integer_payload[1]["data"]["children"][0]["data"]
    integer_post["score"] = 5
    integer_post["upvote_ratio"] = 1
    integer_post["created_utc"] = 1_700_000_000
    integer_comment["score"] = 2

    from_floats = normalize_reddit_thread(float_payload)
    from_integers = normalize_reddit_thread(integer_payload)

    assert from_floats.normalized_sha256 == from_integers.normalized_sha256
    assert (
        from_floats.normalized_content_sha256 == from_integers.normalized_content_sha256
    )


def test_complete_tree_is_classified_only_by_source_tree_exhaustion() -> None:
    result = normalize_reddit_thread(thread_payload(include_more=False))

    assert result.source_tree_exhausted is True
    validation = result.content["validation"]
    assert isinstance(validation, dict)
    assert validation["sourceTreeExhausted"] is True
    # Reddit's reported count remains advisory and may disagree.
    assert validation["counterDeltaClass"] == "exceeds_visible_tree"
