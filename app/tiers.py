"""Subscription tiers — single source of truth.

The site sells three tiers. Each grants access to all catalog content whose
``min_tier`` rank is less than or equal to the buyer's tier rank, for a limited
number of days. Higher rank = more content + longer access.
"""

TIER_LITE = "lite"
TIER_PRO = "pro"
TIER_VIP = "vip"

ALL_TIERS: list[str] = [TIER_LITE, TIER_PRO, TIER_VIP]

# Rank drives content gating: a user sees content with min_tier rank <= his rank.
TIER_RANK: dict[str, int] = {
    TIER_LITE: 1,
    TIER_PRO: 2,
    TIER_VIP: 3,
}

# How long access lasts, per tier. Matches the site copy (Lite/Pro 30 days, VIP 90).
TIER_DURATION_DAYS: dict[str, int] = {
    TIER_LITE: 30,
    TIER_PRO: 30,
    TIER_VIP: 90,
}

TIER_TITLES: dict[str, str] = {
    TIER_LITE: "Lite",
    TIER_PRO: "Pro",
    TIER_VIP: "VIP",
}


def is_valid_tier(tier: str | None) -> bool:
    return tier in TIER_RANK


def normalize_tier(tier: str | None) -> str:
    cleaned = (tier or "").strip().lower()
    if cleaned not in TIER_RANK:
        raise ValueError(f"Unknown tier: {tier!r}")
    return cleaned


def tier_rank(tier: str | None) -> int:
    return TIER_RANK.get((tier or "").strip().lower(), 0)


def tier_title(tier: str | None) -> str:
    cleaned = (tier or "").strip().lower()
    return TIER_TITLES.get(cleaned, cleaned or "—")


def duration_days_for_tier(tier: str) -> int:
    return TIER_DURATION_DAYS[normalize_tier(tier)]
