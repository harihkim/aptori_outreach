"""Deterministic Reddit normalization replayed from verified raw evidence.

This module mirrors the frozen ADR-012 reference normalizer's public content
contract. It deliberately accepts raw JSON, not an observation's precomputed
``normalized`` projection, so callers can enforce raw-evidence-before-
normalization at the transaction boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

NORMALIZER_VERSION = "reddit-thread/v1"

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class NormalizationError(ValueError):
    """Raw evidence cannot be normalized under the named contract."""


@dataclass(frozen=True, slots=True)
class NormalizedThread:
    """One deterministic result and the identities derived from it."""

    normalizer_version: str
    normalized_sha256: str
    normalized_content_sha256: str
    source_tree_exhausted: bool
    root_external_source_id: str
    content: dict[str, JsonValue]


def _canonical_json(value: JsonValue) -> str:
    """Match the frozen runtime's sorted-key, compact JSON representation."""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_value(value: JsonValue) -> JsonValue:
    """Apply JSON.stringify's integer rendering to parsed Python floats."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    return value


def _sha256_json(value: JsonValue) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def _finite_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _integer(value: object, fallback: int) -> int:
    number = _finite_number(value)
    if number is None or not float(number).is_integer():
        return fallback
    return int(number)


def _created_iso(value: int | float | None) -> str | None:
    if value is None:
        return None
    try:
        rendered = datetime.fromtimestamp(float(value), UTC).isoformat(
            timespec="milliseconds"
        )
    except (OSError, OverflowError, ValueError):
        return None
    return rendered.replace("+00:00", "Z")


def _string_or(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _nullable_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def normalize_reddit_thread(
    payload: object, *, normalizer_version: str = NORMALIZER_VERSION
) -> NormalizedThread:
    """Normalize one Reddit two-listing response deterministically."""
    if not normalizer_version:
        raise NormalizationError("normalizer version must be non-empty")
    listings = _list(payload)
    if len(listings) < 2:
        raise NormalizationError("Reddit response must be a two-listing array")

    first = _mapping(listings[0])
    first_data = _mapping(first.get("data"))
    post_children = _list(first_data.get("children"))
    post_child = _mapping(post_children[0]) if post_children else {}
    post_obj = _mapping(post_child.get("data"))
    post_id_value = post_obj.get("id")
    if not isinstance(post_id_value, str) or not post_id_value:
        raise NormalizationError("Reddit response did not contain a root post")

    created_utc = _finite_number(post_obj.get("created_utc"))
    title_value = post_obj.get("title")
    selftext_value = post_obj.get("selftext")
    post_fullname = _string_or(post_obj.get("name"), f"t3_{post_id_value}")
    is_self = bool(post_obj.get("is_self"))
    is_video = bool(post_obj.get("is_video"))
    post: dict[str, JsonValue] = {
        "id": post_fullname,
        "postId": post_id_value,
        "title": title_value if isinstance(title_value, str) else "",
        "author": _nullable_string(post_obj.get("author")),
        "score": _finite_number(post_obj.get("score")),
        "upvoteRatio": _finite_number(post_obj.get("upvote_ratio")),
        "subreddit": _nullable_string(post_obj.get("subreddit_name_prefixed")),
        "totalReportedComments": _finite_number(post_obj.get("num_comments")),
        "createdUtc": created_utc,
        "createdIso": _created_iso(created_utc),
        "selftext": selftext_value if isinstance(selftext_value, str) else "",
        "permalink": _nullable_string(post_obj.get("permalink")),
        "postType": "self" if is_self else "video" if is_video else "link_or_media",
        "locked": bool(post_obj.get("locked")),
    }

    comments: list[JsonValue] = []
    unresolved_more: list[JsonValue] = []

    def parse_children(children: object, traversal_depth: int = 0) -> None:
        for child_value in _list(children):
            child = _mapping(child_value)
            item = _mapping(child.get("data"))
            kind = child.get("kind")
            item_id = item.get("id")
            if kind == "t1" and isinstance(item_id, str) and item_id:
                author = _nullable_string(item.get("author"))
                body_value = item.get("body")
                body = body_value if isinstance(body_value, str) else ""
                comment_created = _finite_number(item.get("created_utc"))
                comment: dict[str, JsonValue] = {
                    "id": _string_or(item.get("name"), f"t1_{item_id}"),
                    "commentId": item_id,
                    "author": author,
                    "score": _finite_number(item.get("score")),
                    "depth": _integer(item.get("depth"), traversal_depth),
                    "parentId": _nullable_string(item.get("parent_id")),
                    "createdUtc": comment_created,
                    "createdIso": _created_iso(comment_created),
                    "body": body,
                    "visibility": (
                        "deleted"
                        if author == "[deleted]" or body == "[deleted]"
                        else "removed"
                        if body == "[removed]"
                        else "visible"
                    ),
                }
                comments.append(comment)
                replies = _mapping(item.get("replies"))
                reply_data = _mapping(replies.get("data"))
                parse_children(reply_data.get("children"), traversal_depth + 1)
            elif kind == "more" and item:
                children_value = item.get("children")
                child_ids: list[JsonValue] = []
                if isinstance(children_value, list):
                    child_ids = cast(list[JsonValue], children_value)
                unresolved_more.append(
                    {
                        "id": _nullable_string(item.get("id")),
                        "parentId": _nullable_string(item.get("parent_id")),
                        "count": _finite_number(item.get("count")) or 0,
                        "childIds": child_ids,
                        "depth": _integer(item.get("depth"), traversal_depth),
                    }
                )

    second = _mapping(listings[1])
    second_data = _mapping(second.get("data"))
    parse_children(second_data.get("children"))

    comment_dicts = [cast(dict[str, JsonValue], item) for item in comments]
    ids = [cast(str, comment["id"]) for comment in comment_dicts]
    id_set = set(ids)
    duplicate_ids: list[JsonValue] = []
    seen_duplicates: set[str] = set()
    for index, comment_id in enumerate(ids):
        if comment_id in ids[:index] and comment_id not in seen_duplicates:
            seen_duplicates.add(comment_id)
            duplicate_ids.append(comment_id)
    missing_parents: list[JsonValue] = [
        {"id": comment["id"], "parentId": comment["parentId"]}
        for comment in comment_dicts
        if comment["parentId"] != post_fullname and comment["parentId"] not in id_set
    ]
    unresolved_child_count = sum(
        len(cast(list[JsonValue], cast(dict[str, JsonValue], item)["childIds"]))
        for item in unresolved_more
    )
    total_reported = post["totalReportedComments"]
    reported_delta: int | float | None = None
    if isinstance(total_reported, (int, float)) and not isinstance(
        total_reported, bool
    ):
        reported_delta = total_reported - len(comments)
    if reported_delta is None:
        counter_delta_class = "unknown"
    elif reported_delta == 0:
        counter_delta_class = "match"
    elif reported_delta > 0 and unresolved_child_count >= reported_delta:
        counter_delta_class = "within_unresolved_more"
    elif reported_delta > 0:
        counter_delta_class = "exceeds_visible_tree"
    else:
        counter_delta_class = "negative_counter_lag"

    depths = [cast(int, comment["depth"]) for comment in comment_dicts]
    source_tree_exhausted = not unresolved_more
    validation: dict[str, JsonValue] = {
        "extractedCommentCount": len(comments),
        "uniqueCommentCount": len(id_set),
        "duplicateIds": duplicate_ids,
        "missingParentReferences": missing_parents,
        "maxDepth": max(depths) if depths else None,
        "unresolvedMoreNodeCount": len(unresolved_more),
        "unresolvedMoreChildCount": unresolved_child_count,
        "sourceTreeExhausted": source_tree_exhausted,
        "reportedCommentDelta": reported_delta,
        "counterDeltaClass": counter_delta_class,
    }
    normalized: dict[str, JsonValue] = {
        "post": post,
        "comments": comments,
        "unresolvedMore": unresolved_more,
        "validation": validation,
    }
    normalized_sha256 = _sha256_json(normalized)
    content_identity: dict[str, JsonValue] = {
        "post": {
            "id": post["id"],
            "title": post["title"],
            "author": post["author"],
            "createdUtc": post["createdUtc"],
            "selftext": post["selftext"],
            "permalink": post["permalink"],
        },
        "comments": [
            {
                "id": comment["id"],
                "author": comment["author"],
                "depth": comment["depth"],
                "parentId": comment["parentId"],
                "createdUtc": comment["createdUtc"],
                "body": comment["body"],
                "visibility": comment["visibility"],
            }
            for comment in comment_dicts
        ],
        "unresolvedMore": unresolved_more,
    }
    normalized_content_sha256 = _sha256_json(content_identity)
    normalized["normalizedSha256"] = normalized_sha256
    normalized["normalizedContentSha256"] = normalized_content_sha256
    return NormalizedThread(
        normalizer_version=normalizer_version,
        normalized_sha256=normalized_sha256,
        normalized_content_sha256=normalized_content_sha256,
        source_tree_exhausted=source_tree_exhausted,
        root_external_source_id=post_fullname,
        content=normalized,
    )
