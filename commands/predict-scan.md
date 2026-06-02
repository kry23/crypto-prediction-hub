---
description: Run the full daily prediction scan now (universe-wide, ~5-8 min)
---

Run `python scripts/predict_scan_cli.py` and report the slate inline in chat.

Read the latest predictions saved to predictions.db at the asof timestamp,
group by long/short/wild-card, and present the top-5 in each bucket with
rationale.
