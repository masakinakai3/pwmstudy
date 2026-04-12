# application/AGENTS.md

This directory owns the shared orchestration layer used by both the desktop UI and the web stack.
It converts UI inputs into simulation parameters, runs the simulation pipeline, shapes responses,
and manages shared scenario/export behavior.

## Files And Responsibilities

- `modulation_config.py`
  - maps external `modulation_mode` into internal axes
  - owns labels and normalization helpers
- `simulation_runner.py`
  - owns `run_simulation()`
  - owns `build_web_response()`
  - owns `run_sweep()`
- `simulation_service.py`
  - owns desktop-side display-unit normalization
  - owns export payloads and baseline snapshots
- `scenario_presets.py`
  - owns the shared learning scenario catalog for desktop and web

## Contract Rules

- Keep the external interface centered on `modulation_mode`
- Do not leak legacy fields back into public contracts
- `overmod_view=True` must correspond to unclamped observation behavior
- `build_web_response()` must return JSON-serializable data only
- Response shaping belongs here, not in `webapi/`

## Scenario Rules

Each shared scenario should keep the current schema expectations:

- required keys:
  - `label`
  - `hint`
  - `focus`
  - `learning_objective`
  - `prerequisites`
  - `procedure`
  - `expected_observation`
  - `uncertainty_notes`
  - `recommended_compare_modes`
  - `tags`
  - `sliders`
  - `modulation_mode`
  - `overmod_view`
  - `fft_target`
  - `fft_window`
- `expected_observation` should always include `text`
- metric-based pass/fail hints must remain compatible with the existing UI

## Change Guidance

- Put new shared calculations here only when they coordinate multiple lower-level modules
- Do not move numerical kernels out of `simulation/`
- Do not put HTTP request handling here
- Preserve the compressed plot payload strategy used by the web response

## Must-Recheck After Changes

- `tests/test_simulation.py`
- `docs/web_api_contract.md`
- `docs/user_guide.md`
- `README.md`
