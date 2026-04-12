# ui/AGENTS.md

This directory owns the desktop Matplotlib UI. It should visualize results from `application/`
and should not reimplement simulation logic.

## Main Class

- `visualizer.py`
  - `InverterVisualizer`

## Responsibilities

- slider and mode controls
- scenario application
- overmodulation toggle
- FFT target and window selection
- baseline comparison
- JSON and PNG export
- drawing the 6-panel visualization

## Required Delegation

The desktop UI should delegate instead of recalculating:

- unit normalization -> `normalize_ui_display_params()`
- simulation -> `run_simulation()`
- export payload -> `build_export_payload()`
- baseline snapshot -> `build_baseline_snapshot()`

## Display Structure

Keep the current 6-panel mental model intact unless the task explicitly requires a redesign:

1. reference + carrier
2. switching pattern
3. line voltages + fundamental
4. phase voltage + fundamental
5. phase currents + theory
6. FFT spectrum + RMS/THD info

## Unit Rules

- internal simulation stays SI
- UI display-only conversions:
  - `f_c`: kHz -> Hz
  - `t_d`: us -> s
  - `L`: mH -> H
  - time axis: s -> ms for display

## Change Guidance

- preserve current educational framing
- preserve existing subplot intent and shared-x behavior
- prefer using new fields from `application/` rather than deriving them a second time in the UI
