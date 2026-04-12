# simulation/AGENTS.md

This directory is the numerical engine. Treat it as a pure-function layer with no UI, web,
filesystem, or plotting concerns.

## Modules

- `reference_generator.py`
  - generates normalized three-phase references
- `carrier_generator.py`
  - generates the carrier waveform
- `pwm_comparator.py`
  - sampling-mode processing, PWM comparison, and dead-time leg-state generation
- `inverter_voltage.py`
  - computes line and phase voltages
- `rl_load_solver.py`
  - computes three-phase RL load current
- `fft_analyzer.py`
  - computes FFT magnitudes, RMS, THD, and related metrics

## Hard Boundaries

- No `matplotlib`
- No `fastapi`
- No `plotly`
- No file I/O
- No UI formatting
- No web response shaping

## Numerical Rules

- Inputs and outputs should stay as `np.ndarray` and scalar numeric types
- Prefer NumPy vectorization over Python loops
- Exception:
  - `rl_load_solver.py` may use a sequential update because the state evolution is step-dependent
- Use `np.linspace` for time bases
- Use:
  - `n_points = int(round(T_sim / dt)) + 1`
  - `dt_actual = t[1] - t[0]`
- Use tolerant floating-point comparisons such as `np.allclose(..., atol=1e-10)`

## Naming And Units

- voltage: `v_`
- current: `i_`
- switching signal: `S_`
- leg state: `leg_`
- internal units must remain SI
- if a variable needs a unit hint, prefer inline comments such as `R: float  # [ohm]`

## Physics Invariants

- sinusoidal three-phase references should sum to approximately zero
- third-harmonic and SVPWM zero-sequence injection must preserve line-to-line reference differences
- switching signals should remain in `{0, 1}`
- dead-time leg states should remain in `{-1, 0, +1}`
- ideal line voltages should remain in `{-V_dc, 0, +V_dc}`

## Mode Assumptions

- public mode selection is unified as `modulation_mode`
- this layer may still work with internal axes such as:
  - `reference_mode`
  - `sampling_mode`
  - `clamp_mode`
- `carrier_two_phase` and `space_vector_two_phase` correspond to clamped two-phase behavior
- `limit_linear=False` is the overmodulation observation path

## Testing Focus

Any meaningful change here should be validated against:

- waveform value ranges
- three-phase symmetry
- dead-time behavior
- RL steady-state amplitude versus theory
- FFT and THD expectations
