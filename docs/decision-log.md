# Decision Log

Record important technical or product decisions here.

## Template

### YYYY-MM-DD - Decision title

- Context:
- Decision:
- Consequence:

### 2026-04-03 - MVP first, plaza later

- Context: The original product idea includes data aggregation, a multi-agent investment brain, and a reputation-based strategy plaza. Building all of them in the first autonomous cycle would create excessive scope and reduce the chance of a successful bootstrap.
- Decision: The first MVP will focus only on the data and intelligence layer plus the multi-agent analysis loop. The reputation plaza will remain out of scope until the core report generation flow is stable.
- Consequence: The initial product will be much simpler, easier to test locally, and better suited for autonomous delivery. Community monetization features will be deferred to later phases.

### 2026-04-03 - Fixture-first bootstrap stack

- Context: The PRD requires FastAPI, proxy-aware external requests, SQLite persistence, and a report flow that must still run locally when external APIs or keys are unavailable.
- Decision: The bootstrap slice uses FastAPI + inline server-rendered HTML, `httpx` for proxy-aware requests, standard-library `sqlite3` for recent report persistence, and fixture-first Binance/FRED/event adapters with live-request fallback.
- Consequence: The repo now has a deterministic local MVP path and critical-path tests without introducing a heavy frontend framework, ORM, or multi-agent orchestration dependency.

### 2026-04-03 - Surface source diagnostics in the first report slice

- Context: The acceptance criteria require proxy and external data failures to be discoverable either in logs or directly in the interface.
- Decision: Each analysis run persists per-source status metadata alongside the intelligence/report JSON and renders those statuses on the report page. Live failures fall back to fixtures and are logged as warnings.
- Consequence: The local MVP stays deterministic while still exposing enough diagnostics to validate proxy-aware live paths later.

### 2026-04-03 - Cache the FRED macro snapshot locally for a short window

- Context: The optimize backlog and acceptance criteria call for at least one macro indicator cache, and repeated analysis runs should not depend on a fresh FRED round-trip every time.
- Decision: Successful `DFF` responses are now stored in the existing SQLite database and reused for up to 12 hours before the client attempts another live fetch.
- Consequence: Repeated analysis runs are faster and less dependent on immediate FRED availability, but the macro snapshot can lag the remote source by up to 12 hours unless the cache expires.

### 2026-04-03 - Keep bootstrap verification self-contained in the offline factory environment

- Context: The factory sandbox cannot install third-party packages from PyPI during bootstrap verification, but the MVP still needs to run its FastAPI-style web flow and `httpx`-style client tests locally.
- Decision: Add tiny in-repo compatibility shims for the subset of `fastapi` and `httpx` used by the current MVP and its tests, while keeping the application code on the same public interfaces.
- Consequence: `python -m unittest discover -s tests -p "test_*.py"` now passes directly from the repo root without network access. The shims intentionally cover only the current bootstrap surface and are not a replacement for the full upstream libraries in later phases.

### 2026-04-30 - Parallelize independent source fetches inside one analysis run

- Context: A single analysis run waits on three independent upstream inputs: Binance market data, the FRED macro snapshot, and the event feed. Running them serially adds their latencies together and slows the core report flow without improving result quality.
- Decision: Dispatch the three source collection steps concurrently with `asyncio.gather(...)`, while keeping per-source fallback handling and the rendered status order unchanged.
- Consequence: End-to-end analysis latency is reduced for live or slow mock sources, but one run now issues its outbound requests in a short burst instead of a strict sequence. This trades a small increase in concurrent upstream load for materially better responsiveness.
