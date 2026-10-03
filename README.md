# GQH 2026: the month-end rebalancing tax on ES/ZN

Tests whether a month-end 60/40 rebalancing-flow trade on ES/ZN futures works better
when it is gated on how much of the expected move has already happened.

**Pre-registered:** see [HYPOTHESIS.md](HYPOTHESIS.md) and `config/frozen.yaml`, committed
under the tag `prereg-final`. Neither file changes after that tag; corrections go in
`AMENDMENTS.md` (bug fixes and data facts only).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Tests

```bash
python -m pytest
```

Tests are deterministic and use no network access and no market data.

## Data

- Put your Databento key in `.env` (copy `.env.example`): `DATABENTO_API_KEY=...`.
- Raw licensed data (`data/`, `*.dbn`, `*.dbn.zst`) is never committed.
