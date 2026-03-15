from __future__ import annotations


def sanitize_untrusted_text(value: str) -> str:
    """Drop control characters from untrusted content."""
    return "".join(ch for ch in value if ch.isprintable())

