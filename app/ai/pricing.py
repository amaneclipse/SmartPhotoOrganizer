"""Token pricing for known models. Prices are USD per 1M tokens.

Only models with known pricing are listed. Unknown models return None,
which means the budget cannot be enforced for them — see AIManager.
"""
from __future__ import annotations

# (input_usd_per_1m, output_usd_per_1m)
_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI (актуальные цены на момент Phase 2; при изменении тарифов — обновить)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
}


def estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Return estimated cost in USD, or None if model/tokens unknown."""
    if input_tokens is None and output_tokens is None:
        return None
    price = _PRICING.get(model)
    if price is None:
        return None
    price_in, price_out = price
    in_tokens = input_tokens or 0
    out_tokens = output_tokens or 0
    return (in_tokens * price_in + out_tokens * price_out) / 1_000_000
