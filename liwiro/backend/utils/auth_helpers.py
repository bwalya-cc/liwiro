# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations


MAX_USERNAME_VARIANTS = 64


def normalize_username(username: str) -> str:
    """Canonical username representation for persistence and comparisons."""
    return str(username or "").strip().lower()


def username_variants(username: str, max_variants: int = MAX_USERNAME_VARIANTS) -> list[str]:
    """Generate a bounded set of username case variants for auth fallbacks."""
    base = normalize_username(username)
    if not base:
        return []

    variants: list[str] = [base, base.lower(), base.upper(), base.capitalize(), base.title()]
    letters = [idx for idx, ch in enumerate(base) if ch.isalpha()]

    # Keep fallback breadth but cap total candidates to avoid request storms.
    if 0 < len(letters) <= 10:
        for mask in range(1 << len(letters)):
            if len(variants) >= max_variants:
                break
            chars = list(base)
            for bit, idx in enumerate(letters):
                chars[idx] = chars[idx].upper() if (mask & (1 << bit)) else chars[idx].lower()
            variants.append("".join(chars))

    out: list[str] = []
    seen = set()
    for variant in variants:
        if variant in seen:
            continue
        seen.add(variant)
        out.append(variant)
        if len(out) >= max_variants:
            break
    return out
