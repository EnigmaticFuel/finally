---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-08-13T15:19:49.590Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 03 | stub | backend/app/services/trading.py | 158 | Sell arm stubbed with TradeError; pinned location replaced by plan 03-02 | open |  | 2026-08-13T15:19:49.590Z |  |

````json
[
  {
    "id": 1,
    "kind": "stub",
    "phase": "03",
    "file": "backend/app/services/trading.py",
    "line": 158,
    "description": "Sell arm stubbed with TradeError; pinned location replaced by plan 03-02",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-13T15:19:49.590Z",
    "resolved_at": null
  }
]
````
