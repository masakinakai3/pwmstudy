const defaultDisplayValues = {
  V_dc: 300.0,
  V_ll_rms: 141.0,
  f: 50.0,
  f_c_khz: 5.0,
  t_d_us: 0.0,
  V_on: 0.0,
  R: 10.0,
  L_mh: 10.0,
  modulation_mode: "carrier",
  overmod_view: false,
  fft_target: "v_uv",
  fft_window: "hann",
  show_u_ref: true,
  show_v_ref: true,
  show_w_ref: true,
  show_line_v_uv: true,
  show_line_v_vw: false,
  show_line_v_wu: false,
};

let scenarioPresets = [];
let currentResponse = null;
let baselineResponse = null;
let debounceHandle = null;
let scenarioFetchFailed = false;
let svpwmAnimationTimer = null;
let svpwmAnimationState = null;
let svpwmAnimationPaused = false;

const SVPWM_ANIMATION_BASE_INTERVAL_MS = 40;

const modulationModeHints = {
  carrier: "三角波比較: 正弦波基準をキャリアと比較する基本方式です。",
  carrier_third_harmonic: "三角波比較(三倍高調波): 零相三倍高調波を加えて線形変調範囲を広げます。",
  carrier_two_phase: "三角波比較(二相変調): 三角波比較ベースで60度クランプを入れる不連続変調です。",
  space_vector: "空間ベクトル: Min-Max 零相注入による連続 SVPWM 相当です。",
  space_vector_two_phase: "空間ベクトル(二相変調): 空間ベクトルベースで60度クランプを入れる不連続変調です。",
};

const SQRT3 = Math.sqrt(3.0);

function buildModulationHint(modulationMode) {
  return `${modulationModeHints[modulationMode]} サンプリング方式は Natural 固定です。`;
}

function isSpaceVectorMode(modulationMode) {
  return modulationMode === "space_vector" || modulationMode === "space_vector_two_phase";
}

function toAlphaBeta(u, v, w) {
  const alpha = (2.0 / 3.0) * (u - 0.5 * v - 0.5 * w);
  const beta = (2.0 / 3.0) * ((SQRT3 / 2.0) * (v - w));
  return { alpha, beta };
}

function inferTwoPhaseZeroVector(u, v, w) {
  const maxRef = Math.max(u, v, w);
  const minRef = Math.min(u, v, w);
  const distToPos = Math.abs(1.0 - maxRef);
  const distToNeg = Math.abs(-1.0 - minRef);
  return distToPos <= distToNeg ? "V7" : "V0";
}

function buildSvpwmWindowFromAlphaBeta(alphaNow, betaNow, switchingPeriod, zeroVector = null) {
  const angleRaw = Math.atan2(betaNow, alphaNow);
  const angle = angleRaw >= 0 ? angleRaw : angleRaw + 2.0 * Math.PI;
  const sector = Math.floor(angle / (Math.PI / 3.0)) + 1;
  const thetaInSector = angle - (sector - 1) * (Math.PI / 3.0);
  const modulationMag = Math.hypot(alphaNow, betaNow);

  const gain = SQRT3 * modulationMag;
  const t1Raw = switchingPeriod * gain * Math.sin(Math.PI / 3.0 - thetaInSector);
  const t2Raw = switchingPeriod * gain * Math.sin(thetaInSector);
  const t1 = Math.max(0.0, Math.min(switchingPeriod, t1Raw));
  const t2 = Math.max(0.0, Math.min(switchingPeriod - t1, t2Raw));
  const t0 = Math.max(0.0, switchingPeriod - t1 - t2);

  const firstVector = `V${sector}`;
  const secondVector = `V${(sector % 6) + 1}`;
  const useSingleZeroVector = zeroVector === "V0" || zeroVector === "V7";
  const primaryZeroLabel = zeroVector === "V7" ? "V7" : "V0";
  const sequenceStates = useSingleZeroVector
    ? [
      primaryZeroLabel,
      firstVector,
      secondVector,
      primaryZeroLabel,
      secondVector,
      firstVector,
      primaryZeroLabel,
    ]
    : [
      "V0",
      firstVector,
      secondVector,
      "V7",
      secondVector,
      firstVector,
      "V0",
    ];

  const t0Half = 0.5 * t0;
  const segmentDurations = [
    0.5 * t0Half,
    0.5 * t1,
    0.5 * t2,
    t0Half,
    0.5 * t2,
    0.5 * t1,
    0.5 * t0Half,
  ];
  const eventTimes = [0.0];
  for (let i = 0; i < segmentDurations.length; i += 1) {
    eventTimes.push(eventTimes[i] + segmentDurations[i]);
  }

  return {
    alphaNow,
    betaNow,
    sector,
    thetaInSector,
    t1,
    t2,
    t0,
    switchingPeriod,
    sequenceStates,
    sequence: sequenceStates.join(" -> "),
    event_times_rel_s: eventTimes,
  };
}

function computeSvpwmSnapshot(data) {
  const u = data.reference.u;
  const v = data.reference.v;
  const w = data.reference.w;
  const isTwoPhaseSvpwm = data.meta.modulation_mode === "space_vector_two_phase";
  const n = Math.min(u.length, v.length, w.length);
  if (n === 0) {
    return null;
  }

  const alpha = new Array(n);
  const beta = new Array(n);
  for (let i = 0; i < n; i += 1) {
    const clarke = toAlphaBeta(u[i], v[i], w[i]);
    alpha[i] = clarke.alpha;
    beta[i] = clarke.beta;
  }

  const snapshotIndex = n - 1;
  const switchingPeriod = 1.0 / data.params.f_c;
  const alphaNow = alpha[snapshotIndex];
  const betaNow = beta[snapshotIndex];
  const zeroVector = isTwoPhaseSvpwm
    ? inferTwoPhaseZeroVector(u[snapshotIndex], v[snapshotIndex], w[snapshotIndex])
    : null;
  const windowNow = buildSvpwmWindowFromAlphaBeta(alphaNow, betaNow, switchingPeriod, zeroVector);

  return {
    alpha,
    beta,
    ...windowNow,
  };
}

function buildSvpwmPatternStep(signalStates, eventTimesRelS, stateLabel) {
  const xUs = [];
  const y = [];
  for (let i = 0; i < signalStates.length; i += 1) {
    const startUs = eventTimesRelS[i] * 1.0e6;
    const endUs = eventTimesRelS[i + 1] * 1.0e6;
    const active = signalStates[i] === stateLabel ? 1.0 : 0.0;
    xUs.push(startUs, endUs);
    y.push(active, active);
  }
  return { xUs, y };
}

function normalizeSvpwmPatternEventTimes(svpwmSnapshot, sequenceLength) {
  const raw = Array.isArray(svpwmSnapshot.event_times_rel_s)
    ? svpwmSnapshot.event_times_rel_s
    : [];
  if (raw.length === sequenceLength + 1) {
    return raw;
  }

  if (
    Number.isFinite(svpwmSnapshot.t0)
    && Number.isFinite(svpwmSnapshot.t1)
    && Number.isFinite(svpwmSnapshot.t2)
  ) {
    const t0Half = 0.5 * svpwmSnapshot.t0;
    const segmentDurations = [
      0.5 * t0Half,
      0.5 * svpwmSnapshot.t1,
      0.5 * svpwmSnapshot.t2,
      t0Half,
      0.5 * svpwmSnapshot.t2,
      0.5 * svpwmSnapshot.t1,
      0.5 * t0Half,
    ];
    const recovered = [0.0];
    for (let i = 0; i < segmentDurations.length; i += 1) {
      recovered.push(recovered[i] + segmentDurations[i]);
    }
    return recovered;
  }

  return raw;
}

function renderSvpwmPatternPlot(svpwmSnapshot, cursorRelS = null) {
  const sequenceStates = svpwmSnapshot.sequenceStates || [];
  const eventTimesRelS = normalizeSvpwmPatternEventTimes(svpwmSnapshot, sequenceStates.length);
  if (sequenceStates.length === 0 || eventTimesRelS.length !== sequenceStates.length + 1) {
    Plotly.react("svpwmPatternPlot", [], {
      ...plotTheme,
      title: "1キャリア周期ベクトル時系列",
      xaxis: { ...plotTheme.xaxis, title: "時間 [us]" },
      yaxis: { ...plotTheme.yaxis, visible: false },
      annotations: [
        {
          text: "時系列データなし",
          showarrow: false,
          xref: "paper",
          yref: "paper",
          x: 0.5,
          y: 0.5,
          font: { size: 14, color: "#5b6468" },
        },
      ],
    }, { responsive: true, displayModeBar: false });
    return;
  }

  const activeVectors = sequenceStates.filter((label) => label !== "V0" && label !== "V7");
  const aVector = activeVectors[0] || "V?";
  const bVector = activeVectors.find((label) => label !== aVector) || "V?";
  const mappedStates = sequenceStates.map((label) => {
    if (label === "V0") {
      return "v0";
    }
    if (label === "V7") {
      return "v7";
    }
    if (label === aVector) {
      return "a";
    }
    if (label === bVector) {
      return "b";
    }
    return "v0";
  });

  const aSeries = buildSvpwmPatternStep(mappedStates, eventTimesRelS, "a");
  const bSeries = buildSvpwmPatternStep(mappedStates, eventTimesRelS, "b");
  const v0Series = buildSvpwmPatternStep(mappedStates, eventTimesRelS, "v0");
  const v7Series = buildSvpwmPatternStep(mappedStates, eventTimesRelS, "v7");

  const periodS = Number.isFinite(svpwmSnapshot.switchingPeriod)
    ? svpwmSnapshot.switchingPeriod
    : eventTimesRelS[eventTimesRelS.length - 1];
  let cursorUs = null;
  if (Number.isFinite(cursorRelS) && Number.isFinite(periodS) && periodS > 0.0) {
    const wrapped = ((cursorRelS % periodS) + periodS) % periodS;
    cursorUs = wrapped * 1.0e6;
  }

  Plotly.react("svpwmPatternPlot", [
    {
      x: aSeries.xUs,
      y: aSeries.y,
      name: `a vector (${aVector})`,
      mode: "lines",
      line: { color: "#c14f2c", width: 2.4, shape: "hv" },
      fill: "tozeroy",
      opacity: 0.5,
    },
    {
      x: bSeries.xUs,
      y: bSeries.y,
      name: `b vector (${bVector})`,
      mode: "lines",
      line: { color: "#4e7a76", width: 2.4, shape: "hv" },
      fill: "tozeroy",
      opacity: 0.5,
    },
    {
      x: v0Series.xUs,
      y: v0Series.y,
      name: "0 vector (V0)",
      mode: "lines",
      line: { color: "#182126", width: 2.0, shape: "hv", dash: "dot" },
    },
    {
      x: v7Series.xUs,
      y: v7Series.y,
      name: "7 vector (V7)",
      mode: "lines",
      line: { color: "#6a5495", width: 2.0, shape: "hv", dash: "dash" },
    },
  ], {
    ...plotTheme,
    title: {
      text: `1キャリア周期: a / b / V0 / V7 ベクトル時系列 (Sector ${svpwmSnapshot.sector})`,
      x: 0.02,
      xanchor: "left",
      font: { size: 14 },
    },
    margin: { ...plotTheme.margin, t: 88 },
    legend: {
      orientation: "h",
      x: 0,
      y: 1.02,
      yanchor: "bottom",
      font: { size: 10 },
    },
    xaxis: { ...plotTheme.xaxis, title: "時間 [us]" },
    yaxis: {
      ...plotTheme.yaxis,
      title: "active",
      range: [-0.05, 1.05],
      tickvals: [0, 1],
      ticktext: ["0", "1"],
    },
    shapes: cursorUs === null
      ? []
      : [
        {
          type: "line",
          x0: cursorUs,
          x1: cursorUs,
          y0: 0.0,
          y1: 1.0,
          line: { color: "rgba(24,33,38,0.9)", width: 2 },
        },
      ],
  }, { responsive: true, displayModeBar: false });
}

function updateSection1Header(data, svpwmSnapshot) {
  const title = document.getElementById("section1Title");
  const refToggles = document.getElementById("section1ReferenceToggles");
  const animationControls = document.getElementById("section1AnimationControls");
  const svInfo = document.getElementById("section1SvpwmInfo");
  const inSpaceVectorMode = isSpaceVectorMode(data.meta.modulation_mode);

  if (!inSpaceVectorMode || !svpwmSnapshot) {
    title.textContent = "変調信号 + キャリア";
    refToggles.hidden = false;
    animationControls.hidden = true;
    svInfo.hidden = true;
    svInfo.innerHTML = "";
    return;
  }

  title.textContent = "空間ベクトル: セクタと1キャリア合成";
  refToggles.hidden = true;
  animationControls.hidden = false;
  svInfo.hidden = true;
  svInfo.innerHTML = "";
}

const controlDefinitions = [
  { key: "V_dc", label: "V_dc", min: 100, max: 600, step: 1, unit: "V" },
  { key: "V_ll_rms", label: "V_LL(rms)", min: 0, max: 450, step: 1, unit: "V" },
  { key: "f", label: "f", min: 1, max: 200, step: 1, unit: "Hz" },
  { key: "f_c_khz", label: "f_c", min: 1, max: 20, step: 0.1, unit: "kHz" },
  { key: "t_d_us", label: "t_d", min: 0, max: 10, step: 0.1, unit: "us" },
  { key: "V_on", label: "V_on", min: 0, max: 5, step: 0.05, unit: "V" },
  { key: "R", label: "R", min: 0.1, max: 100, step: 0.1, unit: "ohm" },
  { key: "L_mh", label: "L", min: 0.1, max: 100, step: 0.1, unit: "mH" },
];

const metricDefinitions = [
  { key: "m_a", label: "m_a", digits: 3 },
  { key: "m_f", label: "m_f", digits: 1 },
  { key: "THD_V", label: "THD_V [%]", digits: 1 },
  { key: "THD_I", label: "THD_I [%]", digits: 1 },
  { key: "V_LL_rms_out", label: "V_LL,out,fund(rms) [V]", digits: 1 },
  { key: "V_LL_rms_total", label: "V_LL,total(rms) [V]", digits: 1 },
  { key: "I_rms", label: "I_rms [A]", digits: 2 },
  { key: "pf1_fft", label: "PF1", digits: 3 },
  { key: "I1_pk", label: "I1_pk [A]", digits: 2 },
];

const plotTheme = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(255,255,255,0.72)",
  font: {
    family: "Aptos, Segoe UI Variable, Yu Gothic UI, sans-serif",
    color: "#182126",
  },
  margin: { l: 54, r: 20, t: 48, b: 42 },
  xaxis: { gridcolor: "rgba(24,33,38,0.08)", zerolinecolor: "rgba(24,33,38,0.1)" },
  yaxis: { gridcolor: "rgba(24,33,38,0.08)", zerolinecolor: "rgba(24,33,38,0.1)" },
  legend: { orientation: "h", yanchor: "bottom", y: 1.02, x: 0 },
};

function debounceRun(callback, delay) {
  clearTimeout(debounceHandle);
  debounceHandle = window.setTimeout(callback, delay);
}

function formatNumber(value, digits) {
  return Number(value).toFixed(digits);
}

function setStatus(badgeText, message, isError = false) {
  const badge = document.getElementById("apiStatus");
  const detail = document.getElementById("statusMessage");
  badge.textContent = badgeText;
  detail.textContent = message;
  badge.style.background = isError ? "rgba(193, 79, 44, 0.16)" : "rgba(78, 122, 118, 0.12)";
  badge.style.color = isError ? "#c14f2c" : "#4e7a76";
}

function stopSvpwmVectorAnimation() {
  if (svpwmAnimationTimer !== null) {
    window.clearInterval(svpwmAnimationTimer);
    svpwmAnimationTimer = null;
  }
  svpwmAnimationState = null;
  svpwmAnimationPaused = false;
  updateSvpwmAnimationPlayPauseLabel();
}

function updateSvpwmAnimationPlayPauseLabel() {
  const button = document.getElementById("section1AnimPlayPause");
  if (!button) {
    return;
  }
  button.textContent = svpwmAnimationPaused ? "再生" : "停止";
}

function getSvpwmAnimationSpeed() {
  const speedControl = document.getElementById("section1AnimSpeed");
  const speed = Number(speedControl ? speedControl.value : 1.0);
  if (!Number.isFinite(speed) || speed <= 0.0) {
    return 1.0;
  }
  return speed;
}

function getSvpwmAnimationIntervalMs() {
  return Math.max(10, Math.round(SVPWM_ANIMATION_BASE_INTERVAL_MS / getSvpwmAnimationSpeed()));
}

function applySvpwmAnimationFrame(pointIndex) {
  if (!svpwmAnimationState) {
    return;
  }

  const {
    plotId,
    alphaSeries,
    betaSeries,
    trailTraceIndex,
    headTraceIndex,
    onFrame,
    windows,
  } = svpwmAnimationState;

  if (windows && windows.length > 0) {
    const windowCount = windows.length;
    const wrappedIndex = ((pointIndex % windowCount) + windowCount) % windowCount;
    svpwmAnimationState.cursor = wrappedIndex;
    const window = windows[wrappedIndex];
    const trailX = [];
    const trailY = [];
    for (let i = 0; i <= wrappedIndex; i += 1) {
      trailX.push(windows[i].alpha);
      trailY.push(windows[i].beta);
    }
    Plotly.restyle(plotId, { x: [trailX], y: [trailY] }, [trailTraceIndex]);
    Plotly.restyle(
      plotId,
      { x: [[window.alpha]], y: [[window.beta]] },
      [headTraceIndex],
    );
    if (typeof onFrame === "function") {
      onFrame(wrappedIndex);
    }
  } else {
    const n = Math.min(alphaSeries.length, betaSeries.length);
    if (n < 1) {
      return;
    }
    const wrappedIndex = ((pointIndex % n) + n) % n;
    svpwmAnimationState.cursor = wrappedIndex;
    const trailX = alphaSeries.slice(0, wrappedIndex + 1);
    const trailY = betaSeries.slice(0, wrappedIndex + 1);
    Plotly.restyle(plotId, { x: [trailX], y: [trailY] }, [trailTraceIndex]);
    Plotly.restyle(
      plotId,
      { x: [[alphaSeries[wrappedIndex]]], y: [[betaSeries[wrappedIndex]]] },
      [headTraceIndex],
    );
    if (typeof onFrame === "function") {
      onFrame(wrappedIndex);
    }
  }
}

function startSvpwmAnimationTimer() {
  if (!svpwmAnimationState || svpwmAnimationPaused) {
    return;
  }
  if (svpwmAnimationTimer !== null) {
    window.clearInterval(svpwmAnimationTimer);
    svpwmAnimationTimer = null;
  }
  const intervalMs = getSvpwmAnimationIntervalMs();
  svpwmAnimationTimer = window.setInterval(() => {
    if (!svpwmAnimationState) {
      return;
    }
    const step = svpwmAnimationState.windows ? 1 : svpwmAnimationState.stride;
    applySvpwmAnimationFrame(svpwmAnimationState.cursor + step);
  }, intervalMs);
}

function setSvpwmAnimationPaused(paused) {
  svpwmAnimationPaused = paused;
  updateSvpwmAnimationPlayPauseLabel();
  if (svpwmAnimationTimer !== null) {
    window.clearInterval(svpwmAnimationTimer);
    svpwmAnimationTimer = null;
  }
  if (!svpwmAnimationPaused) {
    startSvpwmAnimationTimer();
  }
}

function stepSvpwmAnimation(delta) {
  if (!svpwmAnimationState) {
    return;
  }
  setSvpwmAnimationPaused(true);
  applySvpwmAnimationFrame(svpwmAnimationState.cursor + delta);
}

function startSvpwmVectorAnimation(
  plotId,
  alphaSeries,
  betaSeries,
  trailTraceIndex,
  headTraceIndex,
  onFrame = null,
  windows = null,
) {
  stopSvpwmVectorAnimation();

  const n = windows ? windows.length : Math.min(alphaSeries.length, betaSeries.length);
  if (n < 1) {
    return;
  }

  svpwmAnimationState = {
    plotId,
    alphaSeries,
    betaSeries,
    trailTraceIndex,
    headTraceIndex,
    onFrame,
    windows,
    cursor: 0,
    stride: windows ? 1 : Math.max(1, Math.floor(n / 80)),
  };
  svpwmAnimationPaused = false;
  updateSvpwmAnimationPlayPauseLabel();
  applySvpwmAnimationFrame(0);
  startSvpwmAnimationTimer();
}

function getControlInputs(key) {
  return {
    slider: document.querySelector(`input[type="range"][data-key="${key}"]`),
    number: document.querySelector(`input[type="number"][data-key="${key}"]`),
  };
}

function parseControlValue(rawValue) {
  const text = String(rawValue ?? "").trim();
  if (text === "") {
    return null;
  }

  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function isControlValueValid(definition, value) {
  return value !== null && value >= definition.min && value <= definition.max;
}

function setControlValidity(key, isValid) {
  const { number } = getControlInputs(key);
  if (!number) {
    return;
  }

  number.classList.toggle("input-invalid", !isValid);
  number.setAttribute("aria-invalid", String(!isValid));
}

function updateModulationHint() {
  const modulationMode = document.getElementById("modulationMode").value;
  document.getElementById("modulationHint").textContent = buildModulationHint(modulationMode);
}

function buildControlRow(definition) {
  const wrapper = document.createElement("div");
  wrapper.className = "control-row";

  const label = document.createElement("label");
  const title = document.createElement("span");
  title.textContent = definition.label;
  const meta = document.createElement("span");
  meta.className = "control-meta";
  meta.textContent = `${definition.min} - ${definition.max} ${definition.unit}`;
  label.append(title, meta);

  const inputWrap = document.createElement("div");
  inputWrap.className = "control-inputs";

  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = definition.min;
  slider.max = definition.max;
  slider.step = definition.step;
  slider.value = defaultDisplayValues[definition.key];
  slider.dataset.key = definition.key;

  const number = document.createElement("input");
  number.type = "number";
  number.min = definition.min;
  number.max = definition.max;
  number.step = definition.step;
  number.value = defaultDisplayValues[definition.key];
  number.dataset.key = definition.key;

  slider.addEventListener("input", () => {
    number.value = slider.value;
    setControlValidity(definition.key, true);
    scheduleSimulation();
  });
  number.addEventListener("input", () => {
    const parsedValue = parseControlValue(number.value);
    const isValid = isControlValueValid(definition, parsedValue);

    setControlValidity(definition.key, isValid);
    if (!isValid) {
      return;
    }

    slider.value = String(parsedValue);
    scheduleSimulation();
  });

  inputWrap.append(slider, number);
  wrapper.append(label, inputWrap);

  return wrapper;
}

function applyDisplayValues(values) {
  controlDefinitions.forEach((definition) => {
    if (values[definition.key] === undefined) {
      return;
    }
    const { slider, number } = getControlInputs(definition.key);
    slider.value = values[definition.key];
    number.value = values[definition.key];
    setControlValidity(definition.key, true);
  });
}

function initializeControls() {
  const form = document.getElementById("controlForm");
  controlDefinitions.forEach((definition) => {
    form.appendChild(buildControlRow(definition));
  });

  document.getElementById("modulationMode").value = defaultDisplayValues.modulation_mode;
  document.getElementById("overmodView").checked = defaultDisplayValues.overmod_view;
  document.getElementById("fftTarget").value = defaultDisplayValues.fft_target;
  document.getElementById("fftWindow").value = defaultDisplayValues.fft_window;
  document.getElementById("showURef").checked = defaultDisplayValues.show_u_ref;
  document.getElementById("showVRef").checked = defaultDisplayValues.show_v_ref;
  document.getElementById("showWRef").checked = defaultDisplayValues.show_w_ref;
  document.getElementById("showLineVuv").checked = defaultDisplayValues.show_line_v_uv;
  document.getElementById("showLineVvw").checked = defaultDisplayValues.show_line_v_vw;
  document.getElementById("showLineVwu").checked = defaultDisplayValues.show_line_v_wu;
  updateModulationHint();

  ["modulationMode", "overmodView", "fftTarget", "fftWindow"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      if (id === "modulationMode") {
        updateModulationHint();
      }
      scheduleSimulation();
    });
  });
  ["showURef", "showVRef", "showWRef"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      if (currentResponse) {
        renderPlots(currentResponse);
      }
    });
  });
  ["showLineVuv", "showLineVvw", "showLineVwu"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      if (currentResponse) {
        renderPlots(currentResponse);
      }
    });
  });

  document.getElementById("resetButton").addEventListener("click", () => {
    applyDisplayValues(defaultDisplayValues);
    document.getElementById("modulationMode").value = defaultDisplayValues.modulation_mode;
    document.getElementById("overmodView").checked = defaultDisplayValues.overmod_view;
    document.getElementById("fftTarget").value = defaultDisplayValues.fft_target;
    document.getElementById("fftWindow").value = defaultDisplayValues.fft_window;
    document.getElementById("showURef").checked = defaultDisplayValues.show_u_ref;
    document.getElementById("showVRef").checked = defaultDisplayValues.show_v_ref;
    document.getElementById("showWRef").checked = defaultDisplayValues.show_w_ref;
    document.getElementById("showLineVuv").checked = defaultDisplayValues.show_line_v_uv;
    document.getElementById("showLineVvw").checked = defaultDisplayValues.show_line_v_vw;
    document.getElementById("showLineVwu").checked = defaultDisplayValues.show_line_v_wu;
    updateModulationHint();
    renderScenarioGuide();
    scheduleSimulation();
  });

  document.getElementById("baselineSetButton").addEventListener("click", setBaseline);
  document.getElementById("baselineClearButton").addEventListener("click", clearBaseline);
  document.getElementById("exportJsonButton").addEventListener("click", exportCurrentJson);
  document.getElementById("exportPngButton").addEventListener("click", exportDashboardPng);
}

function collectDisplayValues() {
  const values = {};
  let hasInvalidValue = false;

  controlDefinitions.forEach((definition) => {
    const { number } = getControlInputs(definition.key);
    const parsedValue = parseControlValue(number.value);
    const isValid = isControlValueValid(definition, parsedValue);

    setControlValidity(definition.key, isValid);
    if (!isValid) {
      hasInvalidValue = true;
      return;
    }

    values[definition.key] = parsedValue;
  });

  return hasInvalidValue ? null : values;
}

function collectPayload() {
  const values = collectDisplayValues();
  if (!values) {
    return null;
  }

  return {
    V_dc: values.V_dc,
    V_ll_rms: values.V_ll_rms,
    f: values.f,
    f_c: values.f_c_khz * 1000.0,
    t_d: values.t_d_us * 1.0e-6,
    V_on: values.V_on,
    R: values.R,
    L: values.L_mh / 1000.0,
    modulation_mode: document.getElementById("modulationMode").value,
    overmod_view: document.getElementById("overmodView").checked,
    fft_target: document.getElementById("fftTarget").value,
    fft_window: document.getElementById("fftWindow").value,
  };
}

function renderMetrics(metrics) {
  const grid = document.getElementById("metricGrid");
  grid.innerHTML = "";
  metricDefinitions.forEach((definition) => {
    const card = document.createElement("article");
    card.className = "metric-card";
    const label = document.createElement("p");
    label.textContent = definition.label;
    const value = document.createElement("strong");
    value.textContent = formatNumber(metrics[definition.key], definition.digits);
    card.append(label, value);
    grid.appendChild(card);
  });
}

function renderTheoryPanel(metrics) {
  const panel = document.getElementById("theoryPanel");
  const currentErrorPct = metrics.I_theory > 1.0e-9
    ? Math.abs(metrics.I_measured - metrics.I_theory) / metrics.I_theory * 100.0
    : 0.0;
  const cosPhi = Math.cos(metrics.phi);
  const rows = [
    ["I1 理論 [A]", formatNumber(metrics.I_theory, 2)],
    ["I1 FFT実測 [A]", formatNumber(metrics.I_measured, 2)],
    ["誤差 [%]", formatNumber(currentErrorPct, 1)],
    ["cos(phi)", formatNumber(cosPhi, 3)],
    ["PF1(FFT)", formatNumber(metrics.pf1_fft, 3)],
    ["phi [deg]", formatNumber(metrics.phi * 180.0 / Math.PI, 1)],
  ];
  panel.innerHTML = rows.map(([label, value]) => `
    <div class="detail-row">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `).join("");
}

function renderComparisonPanel() {
  const panel = document.getElementById("comparisonPanel");
  if (!currentResponse) {
    panel.innerHTML = '<div class="detail-row"><span>比較状態</span><strong>データ待機中</strong></div>';
    return;
  }

  if (!baselineResponse) {
    panel.innerHTML = `
      <div class="detail-row"><span>比較状態</span><strong>ベースライン未設定</strong></div>
      <div class="detail-row"><span>案内</span><strong>ベースライン設定で差分比較を開始</strong></div>
    `;
    return;
  }

  const deltaV1 = currentResponse.metrics.V1_pk - baselineResponse.metrics.V1_pk;
  const deltaI1 = currentResponse.metrics.I1_pk - baselineResponse.metrics.I1_pk;
  const deltaThdV = currentResponse.metrics.THD_V - baselineResponse.metrics.THD_V;
  const deltaThdI = currentResponse.metrics.THD_I - baselineResponse.metrics.THD_I;

  panel.innerHTML = [
    ["基準方式", baselineResponse.meta.modulation_summary_label],
    ["ΔV1 [V]", `${deltaV1 >= 0 ? "+" : ""}${formatNumber(deltaV1, 1)}`],
    ["ΔI1 [A]", `${deltaI1 >= 0 ? "+" : ""}${formatNumber(deltaI1, 2)}`],
    ["ΔTHD_V [%]", `${deltaThdV >= 0 ? "+" : ""}${formatNumber(deltaThdV, 1)}`],
    ["ΔTHD_I [%]", `${deltaThdI >= 0 ? "+" : ""}${formatNumber(deltaThdI, 1)}`],
    ["基準 m_a", formatNumber(baselineResponse.metrics.m_a, 3)],
  ].map(([label, value]) => `
    <div class="detail-row">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `).join("");
}

function renderScenarioGuide(index = null) {
  const container = document.getElementById("scenarioButtons");
  container.innerHTML = "";
  scenarioPresets.forEach((scenario, scenarioIndex) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `scenario-button ${scenarioIndex === index ? "" : "secondary"}`;
    button.textContent = scenario.label;
    button.addEventListener("click", () => applyScenario(scenarioIndex));
    container.appendChild(button);
  });

  if (index === null || !scenarioPresets[index]) {
    document.getElementById("scenarioTitle").textContent = "学習シナリオを選択";
    document.getElementById("scenarioFocus").textContent = "目的に応じた条件を即座に呼び出せます。";
    document.getElementById("scenarioHint").textContent = "ヒントはここに表示されます。";
    return;
  }

  const active = scenarioPresets[index];
  document.getElementById("scenarioTitle").textContent = active.label;
  document.getElementById("scenarioFocus").textContent = active.focus || "学習焦点を表示します。";
  document.getElementById("scenarioHint").textContent = active.hint;
}

function applyScenario(index) {
  const scenario = scenarioPresets[index];
  if (!scenario) {
    return;
  }

  applyDisplayValues({
    V_dc: scenario.sliders.V_dc,
    V_ll_rms: scenario.sliders.V_ll,
    f: scenario.sliders.f,
    f_c_khz: scenario.sliders.f_c,
    t_d_us: scenario.sliders.t_d,
    V_on: scenario.sliders.V_on,
    R: scenario.sliders.R,
    L_mh: scenario.sliders.L,
  });
  document.getElementById("modulationMode").value = scenario.modulation_mode;
  document.getElementById("overmodView").checked = Boolean(scenario.overmod_view);
  updateModulationHint();
  document.getElementById("fftTarget").value = scenario.fft_target === "current" ? "i_u" : "v_uv";
  document.getElementById("fftWindow").value = scenario.fft_window;
  renderScenarioGuide(index);
  scheduleSimulation();
}

function renderPlots(data) {
  stopSvpwmVectorAnimation();
  const svpwmPatternCard = document.getElementById("svpwmPatternCard");
  const section1PlotGrid = document.getElementById("section1PlotGrid");

  function setSection1SplitLayout(enabled) {
    if (!section1PlotGrid) {
      return;
    }
    section1PlotGrid.classList.toggle("two-up", enabled);
    section1PlotGrid.classList.toggle("section1-single", !enabled);
  }

  function syncSection1PlotSizes(includePatternPlot) {
    if (!Plotly || !Plotly.Plots || typeof Plotly.Plots.resize !== "function") {
      return;
    }
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const referencePlotElement = document.getElementById("referencePlot");
        if (referencePlotElement) {
          Plotly.Plots.resize(referencePlotElement);
        }
        if (includePatternPlot) {
          const patternPlotElement = document.getElementById("svpwmPatternPlot");
          if (patternPlotElement) {
            Plotly.Plots.resize(patternPlotElement);
          }
        }
      });
    });
  }

  const timeMs = data.time.map((value) => value * 1000.0);
  const carrierPlot = data.carrier_plot || null;
  const carrierTimeMs = carrierPlot
    ? carrierPlot.time.map((value) => value * 1000.0)
    : timeMs;
  const carrierWaveform = carrierPlot ? carrierPlot.waveform : data.carrier;
  const switchingPlot = data.switching_plot || {
    time: data.time,
    u: data.switching.u,
    v: data.switching.v,
    w: data.switching.w,
  };
  const switchingTimeMs = switchingPlot.time.map((value) => value * 1000.0);
  const lineVoltagePlot = data.line_voltage_plot || {
    time: data.time,
    v_uv: data.voltages.v_uv,
    v_vw: data.voltages.v_vw,
    v_wu: data.voltages.v_wu,
    v_uv_fund: data.voltages.v_uv_fund,
  };
  const lineVoltageTimeMs = lineVoltagePlot.time.map((value) => value * 1000.0);
  const phaseVoltagePlot = data.phase_voltage_plot || {
    time: data.time,
    v_uN: data.voltages.v_uN,
    v_uN_fund: data.voltages.v_uN_fund,
  };
  const phaseVoltageTimeMs = phaseVoltagePlot.time.map((value) => value * 1000.0);

  const showURef = document.getElementById("showURef").checked;
  const showVRef = document.getElementById("showVRef").checked;
  const showWRef = document.getElementById("showWRef").checked;
  const showLineVuv = document.getElementById("showLineVuv").checked;
  const showLineVvw = document.getElementById("showLineVvw").checked;
  const showLineVwu = document.getElementById("showLineVwu").checked;
  const inSpaceVectorMode = isSpaceVectorMode(data.meta.modulation_mode);
  const observer = data.svpwm_observer || null;
  const observerEnabled = Boolean(inSpaceVectorMode && observer && observer.enabled);
  let svpwmSnapshot = null;
  if (observerEnabled && observer.windows && observer.windows.length > 0) {
    const activeWindow = observer.windows[observer.windows.length - 1];
    svpwmSnapshot = {
      alpha: observer.alpha,
      beta: observer.beta,
      alphaNow: activeWindow.alpha,
      betaNow: activeWindow.beta,
      sector: activeWindow.sector,
      thetaInSector: activeWindow.theta_in_sector,
      switchingPeriod: observer.switching_period_s,
      t1: activeWindow.t1,
      t2: activeWindow.t2,
      t0: activeWindow.t0,
      sequenceStates: activeWindow.sequence,
      sequence: activeWindow.sequence.join(" -> "),
      event_times_rel_s: activeWindow.event_times_rel_s,
      windowIndex: activeWindow.window_index,
      windowStartS: activeWindow.start_s,
      windowEndS: activeWindow.end_s,
      holdAlpha: observer.carrier_hold.alpha,
      holdBeta: observer.carrier_hold.beta,
    };
  } else if (inSpaceVectorMode) {
    svpwmSnapshot = computeSvpwmSnapshot(data);
    if (svpwmSnapshot) {
      const halfT0 = Math.max(0.0, svpwmSnapshot.t0 * 0.5);
      const segmentDurations = [
        halfT0 * 0.5,
        svpwmSnapshot.t1 * 0.5,
        svpwmSnapshot.t2 * 0.5,
        halfT0,
        svpwmSnapshot.t2 * 0.5,
        svpwmSnapshot.t1 * 0.5,
        halfT0 * 0.5,
      ];
      const eventTimes = [0.0];
      for (let i = 0; i < segmentDurations.length; i += 1) {
        eventTimes.push(eventTimes[i] + segmentDurations[i]);
      }
      svpwmSnapshot.event_times_rel_s = eventTimes;
      svpwmSnapshot.windowIndex = -1;
      svpwmSnapshot.windowStartS = null;
      svpwmSnapshot.windowEndS = null;
      svpwmSnapshot.holdAlpha = [];
      svpwmSnapshot.holdBeta = [];
    }
  }
  updateSection1Header(data, svpwmSnapshot);

  if (inSpaceVectorMode && svpwmSnapshot) {
    setSection1SplitLayout(true);
    svpwmPatternCard.hidden = false;
    const periodS = 1.0 / data.params.f;
    const endTimeS = data.time[data.time.length - 1];
    const startTimeS = Math.max(data.time[0], endTimeS - periodS);
    const oneCycleMask = data.time.map((timeValue) => timeValue >= startTimeS);
    const oneCycleTime = data.time.filter((timeValue) => timeValue >= startTimeS);
    const alphaOneCycle = svpwmSnapshot.alpha.filter((_, index) => oneCycleMask[index]);
    const betaOneCycle = svpwmSnapshot.beta.filter((_, index) => oneCycleMask[index]);
    const uOneCycle = data.reference.u.filter((_, index) => oneCycleMask[index]);
    const vOneCycle = data.reference.v.filter((_, index) => oneCycleMask[index]);
    const wOneCycle = data.reference.w.filter((_, index) => oneCycleMask[index]);
    const isTwoPhaseSvpwm = data.meta.modulation_mode === "space_vector_two_phase";

    let holdAlphaOneCycle = svpwmSnapshot.holdAlpha;
    let holdBetaOneCycle = svpwmSnapshot.holdBeta;
    if (observerEnabled && observer && observer.carrier_hold && observer.carrier_hold.time) {
      const holdMask = observer.carrier_hold.time.map((timeValue) => timeValue >= startTimeS);
      holdAlphaOneCycle = svpwmSnapshot.holdAlpha.filter((_, index) => holdMask[index]);
      holdBetaOneCycle = svpwmSnapshot.holdBeta.filter((_, index) => holdMask[index]);
    }

    const radialBoundAuto = Math.max(
      0.6,
      Math.max(...alphaOneCycle.map(Math.abs)),
      Math.max(...betaOneCycle.map(Math.abs)),
    ) * 1.2;
    const radialBound = Math.max(1.1, radialBoundAuto);
    const alphaMin = Math.min(...alphaOneCycle);
    const alphaMax = Math.max(...alphaOneCycle);
    const betaMin = Math.min(...betaOneCycle);
    const betaMax = Math.max(...betaOneCycle);
    const centerAlpha = 0.5 * (alphaMin + alphaMax);
    const centerBeta = 0.5 * (betaMin + betaMax);
    const halfSpan = Math.max(
      0.55,
      1.15 * Math.max(
        Math.max(Math.abs(alphaMin - centerAlpha), Math.abs(alphaMax - centerAlpha)),
        Math.max(Math.abs(betaMin - centerBeta), Math.abs(betaMax - centerBeta)),
      ),
    );
    const vectorTraces = [];
    for (let k = 0; k < 6; k += 1) {
      const angle = k * Math.PI / 3.0;
      vectorTraces.push({
        x: [0.0, radialBound * Math.cos(angle)],
        y: [0.0, radialBound * Math.sin(angle)],
        mode: "lines",
        name: `V${k + 1}`,
        showlegend: false,
        line: { color: "rgba(24,33,38,0.25)", width: 1, dash: "dot" },
        hoverinfo: "skip",
      });
    }

    const maOneAngles = Array.from({ length: 181 }, (_, index) => (2.0 * Math.PI * index) / 180.0);
    vectorTraces.push({
      x: maOneAngles.map((angle) => Math.cos(angle)),
      y: maOneAngles.map((angle) => Math.sin(angle)),
      mode: "lines",
      name: "m_a = 1.0",
      showlegend: false,
      line: { color: "rgba(24,33,38,0.45)", width: 1.6, dash: "dash" },
      hovertemplate: "m_a=1.0 boundary<extra></extra>",
    });

    vectorTraces.push({
      x: alphaOneCycle,
      y: betaOneCycle,
      mode: "lines",
      name: "v_ref trajectory (last 1 cycle)",
      line: { color: "#4e7a76", width: 2.2 },
    });
    if (holdAlphaOneCycle.length > 0 && holdBetaOneCycle.length > 0) {
      vectorTraces.push({
        x: holdAlphaOneCycle,
        y: holdBetaOneCycle,
        mode: "markers",
        name: "carrier boundary samples",
        showlegend: false,
        marker: { color: "#182126", size: 5, opacity: 0.45 },
      });
    }
    const trailTraceIndex = vectorTraces.length;
    vectorTraces.push({
      x: [alphaOneCycle[0]],
      y: [betaOneCycle[0]],
      mode: "lines",
      name: "animated trajectory",
      line: { color: "#c14f2c", width: 2.2 },
      opacity: 0.95,
    });
    const headTraceIndex = vectorTraces.length;
    vectorTraces.push({
      x: [alphaOneCycle[0]],
      y: [betaOneCycle[0]],
      mode: "markers",
      name: "animated head",
      showlegend: false,
      marker: { color: "#c14f2c", size: 10 },
      hovertemplate: `alpha=%{x:.3f}<br>beta=%{y:.3f}<br>sector=${svpwmSnapshot.sector}<extra></extra>`,
    });

    Plotly.react("referencePlot", vectorTraces, {
      ...plotTheme,
      title: {
        text: "αβ平面ベクトル図（電圧指令1周期）",
        x: 0.02,
        xanchor: "left",
        yanchor: "top",
        font: { size: 14 },
      },
      margin: { ...plotTheme.margin, t: 92, b: 56 },
      legend: {
        orientation: "h",
        x: 0,
        y: 1.02,
        yanchor: "bottom",
        font: { size: 10 },
      },
      xaxis: {
        ...plotTheme.xaxis,
        title: "alpha [p.u.]",
        range: [centerAlpha - halfSpan, centerAlpha + halfSpan],
        zeroline: true,
        automargin: true,
      },
      yaxis: {
        ...plotTheme.yaxis,
        title: "beta [p.u.]",
        range: [centerBeta - halfSpan, centerBeta + halfSpan],
        scaleanchor: "x",
        scaleratio: 1,
        zeroline: true,
        automargin: true,
      },
    }, { responsive: true, displayModeBar: false });

    const windowsToAnimate = observerEnabled && observer && observer.windows ? observer.windows : null;
    startSvpwmVectorAnimation(
      "referencePlot",
      alphaOneCycle,
      betaOneCycle,
      trailTraceIndex,
      headTraceIndex,
      (pointIndex) => {
        if (windowsToAnimate && windowsToAnimate[pointIndex]) {
          const window = windowsToAnimate[pointIndex];
          const windowSnapshot = {
            alphaNow: window.alpha,
            betaNow: window.beta,
            sector: window.sector,
            thetaInSector: window.theta_in_sector,
            t1: window.t1,
            t2: window.t2,
            t0: window.t0,
            switchingPeriod: svpwmSnapshot.switchingPeriod,
            sequenceStates: Array.isArray(window.sequence) ? window.sequence : [],
            event_times_rel_s: Array.isArray(window.event_times_rel_s) ? window.event_times_rel_s : [],
          };
          renderSvpwmPatternPlot(windowSnapshot, 0.0);
        } else if (alphaOneCycle[pointIndex] !== undefined && betaOneCycle[pointIndex] !== undefined) {
          const zeroVector = isTwoPhaseSvpwm
            ? inferTwoPhaseZeroVector(uOneCycle[pointIndex], vOneCycle[pointIndex], wOneCycle[pointIndex])
            : null;
          const dynamicSnapshot = buildSvpwmWindowFromAlphaBeta(
            alphaOneCycle[pointIndex],
            betaOneCycle[pointIndex],
            svpwmSnapshot.switchingPeriod,
            zeroVector,
          );
          renderSvpwmPatternPlot(dynamicSnapshot, 0.0);
        }
      },
      windowsToAnimate,
    );
    const initialWindow = windowsToAnimate && windowsToAnimate[0] ? windowsToAnimate[0] : null;
    if (initialWindow) {
      const initialWindowSnapshot = {
        alphaNow: initialWindow.alpha,
        betaNow: initialWindow.beta,
        sector: initialWindow.sector,
        thetaInSector: initialWindow.theta_in_sector,
        t1: initialWindow.t1,
        t2: initialWindow.t2,
        t0: initialWindow.t0,
        switchingPeriod: svpwmSnapshot.switchingPeriod,
        sequenceStates: Array.isArray(initialWindow.sequence) ? initialWindow.sequence : [],
        event_times_rel_s: Array.isArray(initialWindow.event_times_rel_s) ? initialWindow.event_times_rel_s : [],
      };
      renderSvpwmPatternPlot(initialWindowSnapshot, 0.0);
    } else {
      const zeroVector = isTwoPhaseSvpwm
        ? inferTwoPhaseZeroVector(uOneCycle[0], vOneCycle[0], wOneCycle[0])
        : null;
      const initialSnapshot = buildSvpwmWindowFromAlphaBeta(
        alphaOneCycle[0],
        betaOneCycle[0],
        svpwmSnapshot.switchingPeriod,
        zeroVector,
      );
      renderSvpwmPatternPlot(initialSnapshot, 0.0);
    }
    syncSection1PlotSizes(true);
  } else {
    setSection1SplitLayout(false);
    svpwmPatternCard.hidden = true;
    const referenceTraces = [];

    if (showURef) {
      referenceTraces.push({
        x: timeMs,
        y: data.reference.u,
        name: "u ref",
        line: { color: "#c14f2c", width: 2 },
      });
    }
    if (showVRef) {
      referenceTraces.push({
        x: timeMs,
        y: data.reference.v,
        name: "v ref",
        line: { color: "#4e7a76", width: 2 },
      });
    }
    if (showWRef) {
      referenceTraces.push({
        x: timeMs,
        y: data.reference.w,
        name: "w ref",
        line: { color: "#6a5495", width: 2 },
      });
    }
    referenceTraces.push({
      x: carrierTimeMs,
      y: carrierWaveform,
      name: "carrier",
      line: { color: "#2d3748", width: 1.2, dash: "dot" },
    });

    Plotly.react("referencePlot", referenceTraces, {
      ...plotTheme,
      title: "変調信号とキャリア",
      xaxis: { ...plotTheme.xaxis, title: "時間 [ms]" },
      yaxis: { ...plotTheme.yaxis, title: "正規化振幅" },
    }, { responsive: true, displayModeBar: false });
    syncSection1PlotSizes(false);
    Plotly.purge("svpwmPatternPlot");
  }

  Plotly.react("switchingPlot", [
    {
      x: switchingTimeMs,
      y: switchingPlot.u.map((value) => value + 4),
      customdata: switchingPlot.u,
      name: "S_u",
      mode: "lines",
      line: { color: "#c14f2c", width: 2, shape: "hv" },
      hovertemplate: "S_u: %{customdata}<extra></extra>",
    },
    {
      x: switchingTimeMs,
      y: switchingPlot.v.map((value) => value + 2),
      customdata: switchingPlot.v,
      name: "S_v",
      mode: "lines",
      line: { color: "#4e7a76", width: 2, shape: "hv" },
      hovertemplate: "S_v: %{customdata}<extra></extra>",
    },
    {
      x: switchingTimeMs,
      y: switchingPlot.w,
      customdata: switchingPlot.w,
      name: "S_w",
      mode: "lines",
      line: { color: "#6a5495", width: 2, shape: "hv" },
      hovertemplate: "S_w: %{customdata}<extra></extra>",
    },
  ], {
    ...plotTheme,
    title: "スイッチングパターン",
    xaxis: { ...plotTheme.xaxis, title: "時間 [ms]" },
    yaxis: {
      ...plotTheme.yaxis,
      title: "スイッチング状態",
      tickvals: [0, 1, 2, 3, 4, 5],
      ticktext: ["S_w=0", "S_w=1", "S_v=0", "S_v=1", "S_u=0", "S_u=1"],
      range: [-0.4, 5.4],
    },
  }, { responsive: true, displayModeBar: false });

  const lineVoltageTraces = [];
  if (showLineVuv) {
    lineVoltageTraces.push({
      x: lineVoltageTimeMs,
      y: lineVoltagePlot.v_uv,
      name: "v_uv",
      line: { color: "#c14f2c", width: 2.4, shape: "hv" },
    });
  }
  if (showLineVvw) {
    lineVoltageTraces.push({
      x: lineVoltageTimeMs,
      y: lineVoltagePlot.v_vw,
      name: "v_vw",
      line: { color: "#4e7a76", width: 1.5, shape: "hv" },
      opacity: 0.72,
    });
  }
  if (showLineVwu) {
    lineVoltageTraces.push({
      x: lineVoltageTimeMs,
      y: lineVoltagePlot.v_wu,
      name: "v_wu",
      line: { color: "#6a5495", width: 1.5, shape: "hv" },
      opacity: 0.72,
    });
  }
  lineVoltageTraces.push({
    x: lineVoltageTimeMs,
    y: lineVoltagePlot.v_uv_fund,
    name: "v_uv fundamental",
    line: { color: "#182126", width: 2.2, dash: "dash" },
  });

  Plotly.react("lineVoltagePlot", lineVoltageTraces, {
    ...plotTheme,
    title: "線間電圧 (PWM ステップ観察)",
    xaxis: { ...plotTheme.xaxis, title: "時間 [ms]" },
    yaxis: { ...plotTheme.yaxis, title: "電圧 [V]" },
  }, { responsive: true, displayModeBar: false });

  const phaseVoltageTraces = [
    {
      x: phaseVoltageTimeMs,
      y: phaseVoltagePlot.v_uN,
      name: "v_uN",
      line: { color: "#182126", width: 1.5, shape: "hv" },
      opacity: 0.65,
    },
    {
      x: phaseVoltageTimeMs,
      y: phaseVoltagePlot.v_uN_fund,
      name: "v_uN fundamental",
      line: { color: "#c14f2c", width: 2.4, dash: "dash" },
    },
  ];
  if (baselineResponse) {
    const baselinePhaseVoltagePlot = baselineResponse.phase_voltage_plot || {
      time: baselineResponse.time,
      v_uN_fund: baselineResponse.voltages.v_uN_fund,
    };
    const baselineTimeMs = baselinePhaseVoltagePlot.time.map((value) => value * 1000.0);
    phaseVoltageTraces.push({
      x: baselineTimeMs,
      y: baselinePhaseVoltagePlot.v_uN_fund,
      name: "baseline v_uN fundamental",
      line: { color: "#d97706", width: 2, dash: "dot" },
    });
  }

  Plotly.react("phaseVoltagePlot", phaseVoltageTraces, {
    ...plotTheme,
    title: "相電圧 (基本波比較)",
    xaxis: { ...plotTheme.xaxis, title: "時間 [ms]" },
    yaxis: { ...plotTheme.yaxis, title: "電圧 [V]" },
  }, { responsive: true, displayModeBar: false });

  const currentTraces = [
    { x: timeMs, y: data.currents.i_u, name: "i_u", line: { color: "#c14f2c", width: 2 } },
    { x: timeMs, y: data.currents.i_v, name: "i_v", line: { color: "#4e7a76", width: 2 } },
    { x: timeMs, y: data.currents.i_w, name: "i_w", line: { color: "#6a5495", width: 2 } },
    { x: timeMs, y: data.currents.i_u_theory, name: "i_u theory", line: { color: "#182126", width: 2, dash: "dash" } },
  ];
  if (baselineResponse) {
    const baselineTimeMs = baselineResponse.time.map((value) => value * 1000.0);
    currentTraces.push({
      x: baselineTimeMs,
      y: baselineResponse.currents.i_u,
      name: "baseline i_u",
      line: { color: "#7c3aed", width: 2, dash: "dot" },
    });
  }

  Plotly.react("currentPlot", currentTraces, {
    ...plotTheme,
    title: "相電流",
    xaxis: { ...plotTheme.xaxis, title: "時間 [ms]" },
    yaxis: { ...plotTheme.yaxis, title: "電流 [A]" },
  }, { responsive: true, displayModeBar: false });

  const fftTarget = data.meta.fft_target === "i_u" ? data.fft.i_u : data.fft.v_uv;
  const fftUnit = data.meta.fft_target === "i_u" ? "A" : "V";
  const fftTitle = data.meta.fft_target === "i_u" ? "相電流 i_u FFT" : "線間電圧 v_uv FFT";

  Plotly.react("fftPlot", [{
    x: fftTarget.freq.map((value) => value / 1000.0),
    y: fftTarget.magnitude,
    type: "bar",
    name: "spectrum",
    marker: { color: "#4e7a76" },
  }], {
    ...plotTheme,
    title: `${fftTitle} (${data.meta.fft_window})`,
    xaxis: { ...plotTheme.xaxis, title: "周波数 [kHz]" },
    yaxis: { ...plotTheme.yaxis, title: `振幅 [${fftUnit}]` },
  }, { responsive: true, displayModeBar: false });
}

function setBaseline() {
  if (!currentResponse) {
    return;
  }
  baselineResponse = JSON.parse(JSON.stringify(currentResponse));
  renderComparisonPanel();
  renderPlots(currentResponse);
  setStatus("比較モード", "現在の条件をベースラインとして保存しました。");
}

function clearBaseline() {
  baselineResponse = null;
  renderComparisonPanel();
  if (currentResponse) {
    renderPlots(currentResponse);
  }
  setStatus("比較解除", "ベースライン比較を解除しました。");
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function exportCurrentJson() {
  if (!currentResponse) {
    return;
  }
  const payload = {
    timestamp: new Date().toISOString(),
    controls: collectPayload(),
    response: currentResponse,
    baseline: baselineResponse,
  };
  downloadBlob(
    `web_pulse_export_${new Date().toISOString().replace(/[:.]/g, "-")}.json`,
    new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
  );
  setStatus("JSON保存", "現在の条件と結果を JSON として保存しました。");
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = dataUrl;
  });
}

async function exportDashboardPng() {
  if (!currentResponse) {
    return;
  }

  try {
    const plotIds = [
      "referencePlot",
      "switchingPlot",
      "lineVoltagePlot",
      "phaseVoltagePlot",
      "currentPlot",
      "fftPlot",
    ];
    const images = [];
    for (const plotId of plotIds) {
      const plotElement = document.getElementById(plotId);
      const dataUrl = await Plotly.toImage(plotElement, {
        format: "png",
        width: 1200,
        height: 720,
        scale: 1,
      });
      images.push(await loadImage(dataUrl));
    }

    const canvas = document.createElement("canvas");
    canvas.width = 1600;
  canvas.height = 2420;
    const context = canvas.getContext("2d");
    context.fillStyle = "#f4efe6";
    context.fillRect(0, 0, canvas.width, canvas.height);

    context.fillStyle = "#182126";
    context.font = "bold 42px Georgia";
    context.fillText("Three-Phase PWM Inverter Report", 60, 70);
    context.font = "24px Aptos";
    context.fillText(`timestamp: ${new Date().toLocaleString()}`, 60, 112);
    context.fillText(
      `Mode=${currentResponse.meta.modulation_summary_label}, Overmod=${currentResponse.meta.overmod_view ? "on" : "off"}, FFT=${currentResponse.meta.fft_target}`,
      60,
      146,
    );

    context.font = "bold 26px Aptos";
    context.fillText("Theory Snapshot", 980, 70);
    context.font = "22px Aptos";
    const theoryRows = [
      `m_a = ${formatNumber(currentResponse.metrics.m_a, 3)}`,
      `m_f = ${formatNumber(currentResponse.metrics.m_f, 1)}`,
      `I_theory = ${formatNumber(currentResponse.metrics.I_theory, 2)} A`,
      `I_measured = ${formatNumber(currentResponse.metrics.I_measured, 2)} A`,
      `THD_V = ${formatNumber(currentResponse.metrics.THD_V, 1)} %`,
      `THD_I = ${formatNumber(currentResponse.metrics.THD_I, 1)} %`,
    ];
    theoryRows.forEach((row, rowIndex) => context.fillText(row, 980, 116 + rowIndex * 34));

    const slots = [
      [60, 190],
      [820, 190],
      [60, 910],
      [820, 910],
      [60, 1630],
      [820, 1630],
    ];
    images.forEach((image, imageIndex) => {
      const [x, y] = slots[imageIndex];
      context.drawImage(image, x, y, 700, 420);
    });

    if (baselineResponse) {
      context.font = "bold 24px Aptos";
      context.fillText("Baseline Compare", 60, 2140);
      context.font = "22px Aptos";
      const compareRows = [
        `ΔV1 = ${formatNumber(currentResponse.metrics.V1_pk - baselineResponse.metrics.V1_pk, 1)} V`,
        `ΔI1 = ${formatNumber(currentResponse.metrics.I1_pk - baselineResponse.metrics.I1_pk, 2)} A`,
        `ΔTHD_V = ${formatNumber(currentResponse.metrics.THD_V - baselineResponse.metrics.THD_V, 1)} %`,
        `ΔTHD_I = ${formatNumber(currentResponse.metrics.THD_I - baselineResponse.metrics.THD_I, 1)} %`,
      ];
      compareRows.forEach((row, rowIndex) => context.fillText(row, 60, 2190 + rowIndex * 34));
    }

    canvas.toBlob((blob) => {
      if (!blob) {
        setStatus("PNG保存失敗", "PNG の生成に失敗しました。", true);
        return;
      }
      downloadBlob(
        `web_pulse_export_${new Date().toISOString().replace(/[:.]/g, "-")}.png`,
        blob,
      );
      setStatus("PNG保存", "ダッシュボードを PNG として保存しました。");
    }, "image/png");
  } catch (error) {
    console.error(error);
    setStatus("PNG保存失敗", "PNG の出力処理に失敗しました。", true);
  }
}

async function fetchScenarios() {
  const response = await fetch("/scenarios");
  if (!response.ok) {
    throw new Error(`scenario fetch failed: ${response.status}`);
  }
  scenarioPresets = await response.json();
  scenarioFetchFailed = false;
  renderScenarioGuide();
}

async function runSimulation() {
  try {
    setStatus("計算中", "シミュレーションを再計算しています。");
    const payload = collectPayload();
    if (!payload) {
      setStatus("入力確認", "未入力または範囲外の数値を修正してください。", true);
      return;
    }

    const response = await fetch("/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`simulate failed: ${response.status}`);
    }

    const data = await response.json();
    currentResponse = data;
    renderMetrics(data.metrics);
    renderTheoryPanel(data.metrics);
    renderComparisonPanel();
    renderPlots(data);
    setStatus(
      scenarioFetchFailed ? "API 接続中 / ガイド取得失敗" : "API 接続中",
      scenarioFetchFailed
        ? `Mode=${data.meta.modulation_summary_label}, Overmod=${data.meta.overmod_view ? "on" : "off"}, FFT=${data.meta.fft_target}, API=${data.meta.simulation_api_version} / シナリオ取得失敗`
        : `Mode=${data.meta.modulation_summary_label}, Overmod=${data.meta.overmod_view ? "on" : "off"}, FFT=${data.meta.fft_target}, API=${data.meta.simulation_api_version}`,
      scenarioFetchFailed,
    );
  } catch (error) {
    console.error(error);
    setStatus("API エラー", "シミュレーション結果を取得できませんでした。", true);
  }
}

function scheduleSimulation() {
  debounceRun(runSimulation, 300);
}

window.addEventListener("DOMContentLoaded", async () => {
  initializeControls();
  document.getElementById("section1AnimSpeed").addEventListener("change", () => {
    if (!svpwmAnimationPaused) {
      startSvpwmAnimationTimer();
    }
  });
  document.getElementById("section1AnimPlayPause").addEventListener("click", () => {
    setSvpwmAnimationPaused(!svpwmAnimationPaused);
  });
  document.getElementById("section1AnimPrev").addEventListener("click", () => {
    stepSvpwmAnimation(-1);
  });
  document.getElementById("section1AnimNext").addEventListener("click", () => {
    stepSvpwmAnimation(1);
  });
  updateSvpwmAnimationPlayPauseLabel();
  try {
    await fetchScenarios();
  } catch (error) {
    console.error(error);
    scenarioFetchFailed = true;
    setStatus("API エラー", "シナリオガイドを取得できませんでした。", true);
  }
  scheduleSimulation();
});

window.addEventListener("beforeunload", () => {
  stopSvpwmVectorAnimation();
});