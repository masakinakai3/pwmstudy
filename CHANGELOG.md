# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- N/A

### Changed
- N/A

### Documentation
- N/A

### Commits
- N/A

## [v1.0.0] - 2026-04-05

### Added
- Added MIT License.
- Added `SPDX-License-Identifier: MIT` to all source files (Python / JavaScript / HTML / CSS).
- Advanced mathematical guide (`docs/deep_math_guide.md`): ZOH discrete-time solver derivation, Clarke/Park transforms, SVPWM switching time formulae, THD/PF definitions.
- Web UI Phase 4: learning progress tracker (scenario completion tracking, localStorage persistence).
- Web UI Phase 3: operating diagnostics panel and practice check conditions.
- Web UI Phase 2: usability updates for desktop and web UI (baseline comparison, JSON export/import, URL state sharing).
- Web UI Phase 1: learning insights panel and improved comparison feedback.
- Phase 0: test and scenario count synchronization; documentation alignment.

### Changed
- Updated README license section to MIT.

### Documentation
- Clarified distribution terms in LICENSE and README.
- Added `docs/deep_math_guide.md` with derivations for ZOH solver, SVPWM, THD, and Clarke/Park transforms.

### Commits
- [`d6f295d`](../../commit/d6f295d): Add changelog template and v1.0.0 entry
- [`bd65e73`](../../commit/bd65e73): Add MIT SPDX headers across source files
- [`93e8731`](../../commit/93e8731): Add advanced mathematical guide and documentation links
- [`1efab20`](../../commit/1efab20): Implement Phase 4 learning progress tracker in web UI
- [`040a645`](../../commit/040a645): Implement Phase 3 operating diagnostics and practice checks
- [`50488da`](../../commit/50488da): Implement Phase 2 usability updates for desktop and web UI
- [`af5a308`](../../commit/af5a308): Phase 1: add learning insights and clearer comparison feedback
- [`2de4d68`](../../commit/2de4d68): Phase 0: sync test/scenario counts and docs

## [phase6-v1] - 2026-04

### Added
- SVPWM/DPWM sector shading, time slider, and sector info panel in Section 1 of web UI.
- Explicit DPWM1/DPWM2/DPWM3 mode selection.
- 2-phase and 3-phase modulation selection for both carrier-based PWM and SVPWM.
- Overmodulation view (overmod-view) mode: observe m_a above linear limit.
- U/V/W reference visibility toggles in web UI.
- Scenario guide structure with 9 educational presets; shared between desktop and web UIs (`application/scenario_presets.py`).

### Changed
- Modulation axis refactored into separate `reference_mode`, `sampling_mode`, and `clamp_mode` axes managed by `application/modulation_config.py`.
- `V_ll` treated as RMS throughout — peak conversion performed inside `generate_reference`.
- SVPWM animation: loops second carrier cycle after first cycle completes.
- Carrier waveform visibility improved in web UI.

### Documentation
- Guides and API contracts aligned with new modulation features and labels.
- Web API contract (`docs/web_api_contract.md`) and user guide updated.

### Commits
- [`e7866a3`](../../commit/e7866a3): refactor: separate modulation axes
- [`05b93f1`](../../commit/05b93f1): feat: add explicit DPWM mode selection
- [`4bca77d`](../../commit/4bca77d): feat: enable 2-phase/3-phase modulation selection for carrier-based PWM
- [`d859b92`](../../commit/d859b92): feat: add selectable 2-phase and 3-phase modes for SVPWM
- [`0d660bd`](../../commit/0d660bd): feat: add SVPWM mode across simulation, UI, API, and tests
- [`ee89541`](../../commit/ee89541): feat: add overmod-view checkbox independent from PWM mode
- [`e8a6f22`](../../commit/e8a6f22): fix: treat V_ll as RMS throughout
- [`ffc633b`](../../commit/ffc633b): feat(webui): SVPWM/DPWM時刻スライダーとセクター情報パネルを追加
- [`56aecf5`](../../commit/56aecf5): SECTION2: セクターシェーディング機能を実装
- [`12defac`](../../commit/12defac): webui: add Section1 U/V/W reference visibility toggles
- [`18d539e`](../../commit/18d539e): Enhance scenario guide structure and coverage

## [phase5-v1] - 2026-03

### Added
- Web UI / API migration complete (Phases 1–5): FastAPI backend, Plotly-based 4-section web frontend, Docker support.
- `/health`, `/scenarios`, `/simulate` REST endpoints.
- Docker multi-stage build (`Dockerfile`) and `docker-compose.yml`.
- Non-ideal inverter model: dead time and fixed on-state voltage drop switchable in web/desktop UIs.
- Overmodulation clamp warning and modulation index monitor.
- FFT display toggle: line voltage v_uv ↔ phase current i_u, Hann/Rectangular window selection.
- Theory comparison: fundamental current amplitude shown as theory vs FFT measured values.
- DPWM (two-phase modulation) support.
- Third-harmonic injection and min-max zero-sequence modulation methods.
- 65-test suite covering physics validity, application layer, and API/UI integration.

### Changed
- Simulation engine refactored to pure-function modules under `simulation/`.
- `application/` layer introduced for UI/API shared logic.
- Exact ZOH discrete-time RL load solver (analytical solution using `expm1`) replacing Euler integration.
- 5τ warm-up auto-calculation; steady-state waveforms only displayed.

### Documentation
- `architecture.md`: full system architecture documentation.
- `implementation_plan.md`: six-phase implementation roadmap.
- `web_migration_plan.md`: web migration design notes.
- `docs/user_guide.md`: desktop and web UI usage guide.
- `docs/web_api_contract.md`: REST API contract.

### Commits
- [`3c5c251`](../../commit/3c5c251): feat: web migration Phase 1-5 complete
