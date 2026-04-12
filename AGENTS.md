# AGENTS.md

This repository is a learning simulator for a three-phase two-level PWM inverter.
Codex should treat this file as the top-level operating guide, then read the nearest
child `AGENTS.md` before changing files inside a subdirectory.

## Project Overview

- Core domain: three-phase two-level PWM inverter simulation for learning and visualization
- Frontends:
  - Desktop UI: Matplotlib-based 6-panel visualizer launched from `main.py`
  - Web UI: static `webui/` served by FastAPI
- Shared orchestration: `application/`
- Numerical engine: `simulation/`
- Tests: `tests/test_simulation.py`

## Architecture

```text
main.py
  -> ui.visualizer.InverterVisualizer
  -> application.normalize_ui_display_params()
  -> application.run_simulation()
  -> simulation.*

webui/app.js
  -> POST /simulate or /sweep
  -> webapi.app
  -> application.run_simulation() / run_sweep()
  -> application.build_web_response()
  -> simulation.*
```

## Main Directories

- `application/`: shared orchestration, unit normalization, export, scenario presets
- `simulation/`: pure numerical functions with no UI or web dependencies
- `ui/`: desktop Matplotlib UI
- `webapi/`: FastAPI schema and endpoint layer
- `webui/`: vanilla JS frontend
- `tests/`: physics, contract, UI/API smoke, and regression tests
- `docs/`: user guide, API contract, math notes, architecture and plans

## Setup And Run

```powershell
pip install -r requirements.txt
python main.py
python -m uvicorn webapi.app:app --reload
python -m pytest tests -v
```

## High-Value Invariants

- Keep the external modulation interface unified as `modulation_mode`
- Valid user-facing modes:
  - `carrier`
  - `carrier_third_harmonic`
  - `carrier_two_phase`
  - `space_vector`
  - `space_vector_two_phase`
- Do not reintroduce legacy API fields such as:
  - `pwm_mode`
  - `svpwm_mode`
  - `reference_mode`
  - `sampling_mode`
  - `clamp_mode`
- Internal simulation units must stay SI:
  - voltage: `V`
  - current: `A`
  - frequency: `Hz`
  - time: `s`
  - inductance: `H`
- UI-only display units such as `kHz`, `us`, and `mH` must be converted in the UI or service layer
- Time grids should be created with `np.linspace`, not `np.arange`
- Point count convention:
  - `n_points = int(round(T_sim / dt)) + 1`
  - `dt_actual = t[1] - t[0]`

## Editing Rules

- Prefer minimal, local changes that preserve the current architecture
- Do not duplicate physics logic across `simulation/`, `application/`, `ui/`, and `webapi/`
- Keep physics calculations in `simulation/`
- Keep orchestration and response shaping in `application/`
- Keep request validation in `webapi/schemas.py`
- Keep frontend unit conversion and rendering concerns in `webui/app.js`
- If behavior or API contracts change, update the matching docs in the same pass

## Verification Expectations

- Run the narrowest meaningful test first while iterating
- Run the full test suite before finishing when the change touches shared behavior

Recommended commands:

```powershell
python -m pytest tests -k "SimulationRunnerContract" -v
python -m pytest tests -k "WebApi" -v
python -m pytest tests -v
```

## Documentation Sync

When behavior, UI flow, scenario schema, or API payloads change, review:

- `README.md`
- `docs/user_guide.md`
- `docs/web_api_contract.md`
- `architecture.md`

## Local Guides

Read the nearest file before editing in these directories:

- `application/AGENTS.md`
- `simulation/AGENTS.md`
- `ui/AGENTS.md`
- `webapi/AGENTS.md`
- `webui/AGENTS.md`
- `tests/AGENTS.md`
