# webui/AGENTS.md

This directory contains the static web frontend served by FastAPI.
The stack is intentionally simple: `index.html`, `styles.css`, and `app.js`.

## File Roles

- `index.html`
  - page structure and controls
- `styles.css`
  - layout, theming, and responsive behavior
- `app.js`
  - API calls, state, Plotly rendering, scenario handling, export, and comparisons

## UX And Rendering Rules

- preserve the current educational structure unless the task asks for a broader redesign
- keep the existing card-based layout and visual language coherent
- avoid rewriting large portions of `app.js` unless necessary
- prefer extending current rendering paths over introducing parallel ones

## API Usage

- `GET /scenarios` for scenario metadata
- `POST /simulate` for the main run
- `POST /sweep` for modulation sweeps
- convert display units to SI before sending:
  - `f_c`: kHz -> Hz
  - `t_d`: us -> s
  - `L`: mH -> H

## Plotting Rules

- prefer `Plotly.react()` for full redraws
- prefer `Plotly.restyle()` for lightweight updates when appropriate
- respect backend-provided compressed series for switching and line-voltage plots
- for SVPWM views, prefer backend `svpwm_observer` data over re-deriving timing in the browser
- do not break synchronized animation flows for Section 1 and Section 2

## Shared Content Rules

- scenario rendering must stay compatible with `application/scenario_presets.py`
- comparison and export behavior should remain compatible with the existing payload structure
- keep copy concise and instructional

## Must-Recheck After Changes

- `tests/test_simulation.py`
- `docs/user_guide.md`
- `docs/web_api_contract.md`
