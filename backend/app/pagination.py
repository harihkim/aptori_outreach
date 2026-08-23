"""Opaque, endpoint-scoped cursors for monotonic database positions."""

import base64


class InvalidCursor(ValueError):
    """A cursor is malformed or belongs to a different endpoint."""


def encode_cursor(namespace: str, position: int) -> str:
    payload = f"{namespace}:{position}".encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(namespace: str, cursor: str) -> int:
    if not cursor or len(cursor) > 200:
        raise InvalidCursor(cursor)
    padding = "=" * (-len(cursor) % 4)
    try:
        payload = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        ).decode()
        encoded_namespace, encoded_position = payload.split(":", 1)
        position = int(encoded_position)
    except (UnicodeDecodeError, ValueError) as error:
        raise InvalidCursor(cursor) from error
    if encoded_namespace != namespace or position < 1:
        raise InvalidCursor(cursor)
    return position
