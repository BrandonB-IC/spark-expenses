"""
Currency conversion for the Spark Expense Engine.

v1 stub: passes USD through unchanged. For non-USD receipts, raises a clear
NotImplementedError so we know to wire up exchangerate.host the moment a real
foreign-currency receipt shows up. This is intentional — building the FX
caching layer before we have a real test case is speculative work.

When we DO need FX (v2):
- Use https://api.exchangerate.host/convert?from=EUR&to=USD&date=2026-04-08
- Cache by (date, from, to) in a small JSON file at config/fx_cache.json
- Fall back to month-start rate if the transaction-date rate is unavailable
"""

from __future__ import annotations


def to_usd(amount: float, currency: str, transaction_date: str) -> float:
    """Convert an amount in `currency` on `transaction_date` (YYYY-MM-DD) to USD.

    Raises NotImplementedError for non-USD currencies in v1.
    """
    if not currency or currency.upper() == "USD":
        return float(amount or 0)
    raise NotImplementedError(
        f"Foreign currency conversion not yet implemented for {currency} "
        f"(receipt date {transaction_date}). Add FX support in pipeline/currency.py "
        f"using exchangerate.host before processing this receipt."
    )


def normalize_receipts(receipts: list[dict]) -> list[dict]:
    """Add `amount_usd` to each receipt. v1: passthrough for USD; raises for others.

    The rules engine should use `amount_usd` (not `amount`) for any cross-receipt
    arithmetic so that future FX support drops in cleanly.
    """
    out = []
    for r in receipts:
        r = dict(r)
        r["amount_usd"] = to_usd(
            r.get("amount") or 0,
            r.get("currency") or "USD",
            r.get("date") or "",
        )
        out.append(r)
    return out
