from __future__ import annotations

import re

PHONE_MODEL_LABELS: dict[str, tuple[str, str]] = {
    "IPHONE 15": ("iphone_15", "iPhone 15"),
    "IPHONE 15 PRO": ("iphone_15_pro", "iPhone 15 Pro"),
    "IPHONE 15 PRO MAX": ("iphone_15_pro_max", "iPhone 15 Pro Max"),
    "IPHONE 16": ("iphone_16", "iPhone 16"),
    "IPHONE 16 PLUS": ("iphone_16_plus", "iPhone 16 Plus"),
    "IPHONE 16 PRO": ("iphone_16_pro", "iPhone 16 Pro"),
    "IPHONE 16 PRO MAX": ("iphone_16_pro_max", "iPhone 16 Pro Max"),
    "IPHONE 17": ("iphone_17", "iPhone 17"),
    "IPHONE 17 AIR": ("iphone_17_air", "iPhone 17 Air"),
    "IPHONE 17 PRO": ("iphone_17_pro", "iPhone 17 Pro"),
    "IPHONE 17 PRO MAX": ("iphone_17_pro_max", "iPhone 17 Pro Max"),
    "SAMSUNG GALAXY S26 5G": ("samsung_s26", "Samsung S26"),
    "SAMSUNG GALAXY S26 PLUS 5G": ("samsung_s26_plus", "Samsung S26 Plus"),
    "SAMSUNG GALAXY S26 ULTRA 5G": ("samsung_s26_ultra", "Samsung S26 Ultra"),
}

_KNOWN_MODELS = sorted(PHONE_MODEL_LABELS, key=len, reverse=True)


def _clean_phone_model(raw: str) -> str | None:
    candidate = re.sub(r"[^A-Z0-9]+", " ", raw.upper()).strip()
    for model in _KNOWN_MODELS:
        if candidate.startswith(model):
            return model
    return candidate or None


def extract_phone_model_keys(item_name: str) -> set[str]:
    """Extract normalized phone model names from Romanian product names."""
    normalized = (
        re.sub(r"\s+", " ", str(item_name).upper())
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )
    if " PENTRU " in normalized:
        normalized = normalized.split(" PENTRU ", maxsplit=1)[1]
    normalized = normalized.split(" - ", maxsplit=1)[0].strip()
    if not normalized:
        return set()

    prefix_tokens: list[str] = []
    for token in normalized.split():
        if any(char.isdigit() for char in token):
            break
        prefix_tokens.append(token)
    prefix = " ".join(prefix_tokens)

    models: set[str] = set()
    for part in [part.strip() for part in normalized.split("/") if part.strip()] or [normalized]:
        candidate = part
        if prefix and not candidate.startswith(prefix):
            candidate = f"{prefix} {candidate}"
        model = _clean_phone_model(candidate)
        if model:
            models.add(model)
    return models


def phone_model_metadata(model: str) -> tuple[str, str] | None:
    return PHONE_MODEL_LABELS.get(model)
