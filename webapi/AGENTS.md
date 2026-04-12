# webapi/AGENTS.md

This directory owns the FastAPI boundary only. It validates inputs, delegates to `application/`,
and returns HTTP responses. It must not become a second simulation layer.

## Endpoints

- `GET /`
  - serves the web UI entry point
- `GET /health`
  - returns status and API version
- `GET /scenarios`
  - returns `application.SCENARIO_PRESETS`
- `POST /simulate`
  - validates input and returns `build_web_response(run_simulation(...))`
- `POST /sweep`
  - validates input and returns `run_sweep(...)`

## Schema Rules

- keep input validation in `schemas.py`
- reject unknown fields
- keep the public `fft_target` contract as:
  - `v_uv`
  - `i_u`
- map public API values to internal simulation keys in the schema layer

## Hard Rules

- no physics reimplementation in `app.py`
- no duplicate unit-conversion logic that already belongs in schemas or application
- keep the public interface unified around `modulation_mode`
- do not reintroduce removed legacy fields into request models

## Sync Checklist

If request or response payloads change, update:

- `docs/web_api_contract.md`
- `README.md`
- relevant tests in `tests/test_simulation.py`
