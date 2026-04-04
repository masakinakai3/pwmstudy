const defaultDisplayValues = {
  V_dc: 300.0,
  V_ll_rms: 141.0,
  f: 50.0,
  f_c_khz: 5.0,
  t_d_us: 0.0,
  V_on: 0.0,
  R: 10.0,
  L_mh: 10.0,
  pwm_mode: "natural",
  overmod_view: false,
  svpwm_mode: "three_phase",
  fft_target: "v_uv",
  fft_window: "hann",
  show_u_ref: true,
  show_v_ref: true,
  show_w_ref: true,
};

let scenarioPresets = [];
let currentResponse = null;
let baselineResponse = null;
let debounceHandle = null;
let scenarioFetchFailed = false;

const phaseModulationHints = {
  three_phase: "3相変調: 連続PWM。3相すべてが連続的にスイッチングします。",
  dpwm1: "DPWM1: 山頂・谷底付近で60度クランプし、ピーク時のスイッチングを休止します。",
  dpwm2: "DPWM2: DPWM1 と相補的な位置で60度クランプし、休止区間が半周期ずれます。",
  dpwm3: "DPWM3: 山頂そのものではなく両脇でクランプし、M字型に近い指令波形になります。",
};

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

function updatePhaseModulationHint() {
  const mode = document.getElementById("svpwmMode").value;
  const hint = phaseModulationHints[mode] || phaseModulationHints.three_phase;
  document.getElementById("phaseModulationHint").textContent = hint;
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
    scheduleSimulation();
  });
  number.addEventListener("input", () => {
    slider.value = number.value;
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
    document.querySelector(`input[type="range"][data-key="${definition.key}"]`).value = values[definition.key];
    document.querySelector(`input[type="number"][data-key="${definition.key}"]`).value = values[definition.key];
  });
}

function initializeControls() {
  const form = document.getElementById("controlForm");
  controlDefinitions.forEach((definition) => {
    form.appendChild(buildControlRow(definition));
  });

  document.getElementById("pwmMode").value = defaultDisplayValues.pwm_mode;
  document.getElementById("overmodView").checked = defaultDisplayValues.overmod_view;
  document.getElementById("svpwmMode").value = defaultDisplayValues.svpwm_mode;
  document.getElementById("fftTarget").value = defaultDisplayValues.fft_target;
  document.getElementById("fftWindow").value = defaultDisplayValues.fft_window;
  document.getElementById("showURef").checked = defaultDisplayValues.show_u_ref;
  document.getElementById("showVRef").checked = defaultDisplayValues.show_v_ref;
  document.getElementById("showWRef").checked = defaultDisplayValues.show_w_ref;
  updatePhaseModulationHint();

  ["pwmMode", "overmodView", "svpwmMode", "fftTarget", "fftWindow"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      if (id === "svpwmMode") {
        updatePhaseModulationHint();
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

  document.getElementById("resetButton").addEventListener("click", () => {
    applyDisplayValues(defaultDisplayValues);
    document.getElementById("pwmMode").value = defaultDisplayValues.pwm_mode;
    document.getElementById("overmodView").checked = defaultDisplayValues.overmod_view;
    document.getElementById("svpwmMode").value = defaultDisplayValues.svpwm_mode;
    document.getElementById("fftTarget").value = defaultDisplayValues.fft_target;
    document.getElementById("fftWindow").value = defaultDisplayValues.fft_window;
    document.getElementById("showURef").checked = defaultDisplayValues.show_u_ref;
    document.getElementById("showVRef").checked = defaultDisplayValues.show_v_ref;
    document.getElementById("showWRef").checked = defaultDisplayValues.show_w_ref;
    updatePhaseModulationHint();
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
  controlDefinitions.forEach((definition) => {
    values[definition.key] = Number(
      document.querySelector(`input[type="number"][data-key="${definition.key}"]`).value,
    );
  });
  return values;
}

function collectPayload() {
  const values = collectDisplayValues();
  return {
    V_dc: values.V_dc,
    V_ll_rms: values.V_ll_rms,
    f: values.f,
    f_c: values.f_c_khz * 1000.0,
    t_d: values.t_d_us * 1.0e-6,
    V_on: values.V_on,
    R: values.R,
    L: values.L_mh / 1000.0,
    pwm_mode: document.getElementById("pwmMode").value,
    overmod_view: document.getElementById("overmodView").checked,
    svpwm_mode: document.getElementById("svpwmMode").value,
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
    ["基準 PWM", baselineResponse.meta.pwm_mode],
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
  const phaseModulationMode = scenario.svpwm_mode === "two_phase" ? "dpwm1" : (scenario.svpwm_mode || "three_phase");

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
  document.getElementById("pwmMode").value = scenario.pwm_mode;
  document.getElementById("overmodView").checked = Boolean(scenario.overmod_view);
  document.getElementById("svpwmMode").value = phaseModulationMode;
  updatePhaseModulationHint();
  document.getElementById("fftTarget").value = scenario.fft_target === "current" ? "i_u" : "v_uv";
  document.getElementById("fftWindow").value = scenario.fft_window;
  renderScenarioGuide(index);
  scheduleSimulation();
}

function renderPlots(data) {
  const timeMs = data.time.map((value) => value * 1000.0);
  const carrierPlot = data.carrier_plot || null;
  const carrierTimeMs = carrierPlot
    ? carrierPlot.time.map((value) => value * 1000.0)
    : timeMs;
  const carrierWaveform = carrierPlot ? carrierPlot.waveform : data.carrier;

  const showURef = document.getElementById("showURef").checked;
  const showVRef = document.getElementById("showVRef").checked;
  const showWRef = document.getElementById("showWRef").checked;
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

  const lineVoltageTraces = [
    { x: timeMs, y: data.voltages.v_uv, name: "v_uv", line: { color: "#c14f2c", width: 2 } },
    { x: timeMs, y: data.voltages.v_vw, name: "v_vw", line: { color: "#4e7a76", width: 2 } },
    { x: timeMs, y: data.voltages.v_wu, name: "v_wu", line: { color: "#6a5495", width: 2 } },
    {
      x: timeMs,
      y: data.voltages.v_uv_fund,
      name: "v_uv fundamental",
      line: { color: "#182126", width: 2.2, dash: "dash" },
    },
  ];
  if (baselineResponse) {
    const baselineTimeMs = baselineResponse.time.map((value) => value * 1000.0);
    lineVoltageTraces.push({
      x: baselineTimeMs,
      y: baselineResponse.voltages.v_uv_fund,
      name: "baseline v_uv fundamental",
      line: { color: "#d97706", width: 2, dash: "dot" },
    });
  }

  Plotly.react("lineVoltagePlot", lineVoltageTraces, {
    ...plotTheme,
    title: "線間電圧",
    xaxis: { ...plotTheme.xaxis, title: "時間 [ms]" },
    yaxis: { ...plotTheme.yaxis, title: "電圧 [V]" },
  }, { responsive: true, displayModeBar: false });

  Plotly.react("phaseVoltagePlot", [
    { x: timeMs, y: data.voltages.v_uN, name: "v_uN", line: { color: "#182126", width: 1.8 } },
    { x: timeMs, y: data.voltages.v_uN_fund, name: "v_uN fundamental", line: { color: "#c14f2c", width: 2.2, dash: "dash" } },
  ], {
    ...plotTheme,
    title: "相電圧",
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
    const plotIds = ["referencePlot", "lineVoltagePlot", "phaseVoltagePlot", "currentPlot", "fftPlot"];
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
    canvas.height = 2300;
    const context = canvas.getContext("2d");
    context.fillStyle = "#f4efe6";
    context.fillRect(0, 0, canvas.width, canvas.height);

    context.fillStyle = "#182126";
    context.font = "bold 42px Georgia";
    context.fillText("Three-Phase PWM Inverter Report", 60, 70);
    context.font = "24px Aptos";
    context.fillText(`timestamp: ${new Date().toLocaleString()}`, 60, 112);
    context.fillText(
      `PWM=${currentResponse.meta.pwm_mode}, Overmod=${currentResponse.meta.overmod_view ? "on" : "off"}, FFT=${currentResponse.meta.fft_target}`,
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
    ];
    images.forEach((image, imageIndex) => {
      const [x, y] = slots[imageIndex];
      context.drawImage(image, x, y, 700, 420);
    });

    if (baselineResponse) {
      context.font = "bold 24px Aptos";
      context.fillText("Baseline Compare", 820, 1630);
      context.font = "22px Aptos";
      const compareRows = [
        `ΔV1 = ${formatNumber(currentResponse.metrics.V1_pk - baselineResponse.metrics.V1_pk, 1)} V`,
        `ΔI1 = ${formatNumber(currentResponse.metrics.I1_pk - baselineResponse.metrics.I1_pk, 2)} A`,
        `ΔTHD_V = ${formatNumber(currentResponse.metrics.THD_V - baselineResponse.metrics.THD_V, 1)} %`,
        `ΔTHD_I = ${formatNumber(currentResponse.metrics.THD_I - baselineResponse.metrics.THD_I, 1)} %`,
      ];
      compareRows.forEach((row, rowIndex) => context.fillText(row, 820, 1680 + rowIndex * 34));
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
        ? `PWM=${data.meta.pwm_mode}, Overmod=${data.meta.overmod_view ? "on" : "off"}, FFT=${data.meta.fft_target}, API=${data.meta.simulation_api_version} / シナリオ取得失敗`
        : `PWM=${data.meta.pwm_mode}, Overmod=${data.meta.overmod_view ? "on" : "off"}, FFT=${data.meta.fft_target}, API=${data.meta.simulation_api_version}`,
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
  try {
    await fetchScenarios();
  } catch (error) {
    console.error(error);
    scenarioFetchFailed = true;
    setStatus("API エラー", "シナリオガイドを取得できませんでした。", true);
  }
  scheduleSimulation();
});