from __future__ import annotations

import hashlib


CHECKSUM_MODE_UTF8_TEXT_LF_V1 = "utf8_text_lf_v1"


def canonical_text_sha256(raw_bytes: bytes, checksum_mode: str) -> str:
    """Hash a packaged UTF-8 text artifact independent of BOM and line endings."""
    if checksum_mode != CHECKSUM_MODE_UTF8_TEXT_LF_V1:
        raise ValueError(f"unsupported runtime checksum mode: {checksum_mode}")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("runtime artifact is not valid UTF-8 text") from exc
    canonical_text = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
