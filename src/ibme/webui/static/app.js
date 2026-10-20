(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const state = {
    presets: [], selected: "primary", session: null, config: null, configJSON: null, capacity: {},
    ready: false, busy: true, uncertain: false, receipt: null, receiptJSON: null, decrypt: null,
  };
  const modeNames = {
    normal: "双方身份正确", wrong_sender: "发送者不匹配", wrong_receiver: "接收者不匹配",
    both_wrong: "双方身份都不匹配", tamper: "篡改密文 1 bit", truncate: "截断密文 1 字节",
  };
  const byteLength = (text) => new TextEncoder().encode(text).length;
  const bytes = (n) => {
    if (!Number.isFinite(n)) return "—";
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(1)} KiB`;
    return `${(n / 1048576).toFixed(1)} MiB`;
  };
  const seconds = (n) => {
    if (!Number.isFinite(n)) return "—";
    if (n < 1) return `${Math.round(n * 1000)} ms`;
    if (n < 60) return `${n.toFixed(2)} s`;
    return `${Math.floor(n / 60)} min ${(n % 60).toFixed(1)} s`;
  };
  const text = (tag, content, className) => {
    const el = document.createElement(tag);
    el.textContent = content;
    if (className) el.className = className;
    return el;
  };
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  class ConnectionError extends Error {}

  function connection(online) {
    $("#connection").className = `connection ${online ? "online" : "offline"}`;
    $("#connection span").textContent = online ? "本地服务" : "连接中断";
  }

  async function api(path, body, returnText = false) {
    let response;
    try {
      response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(15000), cache: "no-store",
      });
    } catch (_) {
      connection(false);
      throw new ConnectionError("连接中断。操作可能仍在执行，请重新连接查看。");
    }
    let data, raw;
    try { raw = await response.text(); data = JSON.parse(raw); }
    catch (_) { throw new ConnectionError("服务响应不完整，请重新连接。"); }
    connection(true);
    if (!response.ok) {
      const error = new Error(data.error || `请求失败（${response.status}）`);
      error.status = response.status;
      throw error;
    }
    return returnText ? raw : data;
  }

  function showError(error) {
    $("#errorBanner").hidden = false;
    $("#errorText").textContent = error.message;
    const uncertain = error instanceof ConnectionError || error.status === 409;
    state.uncertain = uncertain;
    $("#reconnectBtn").hidden = !uncertain;
    $("#dismissError").hidden = uncertain;
  }

  function clearError() {
    $("#errorBanner").hidden = true;
    $("#reconnectBtn").hidden = true;
    $("#dismissError").hidden = false;
  }

  function refreshControls() {
    const busy = state.busy || state.uncertain;
    const active = !!state.session;
    const count = byteLength($("#message").value);
    const limit = state.capacity.max_application_bytes;
    const dirty = active && state.session.has_ciphertext && $("#message").value !== state.session.last_message;
    const cipher = !!state.session?.has_ciphertext;
    $("#startBtn").disabled = busy || active || !state.ready;
    $("#startBtn").textContent = active ? "会话已就绪" : "开始演示";
    $("#resetBtn").hidden = !active;
    $("#resetBtn").disabled = busy;
    $("#encryptBtn").disabled = busy || !active || count === 0 || count > limit;
    $("#decryptBtn").disabled = busy || !cipher || dirty;
    $("#testMode").disabled = busy || !cipher;
    $("#exportBtn").disabled = busy || !active;
    $("#message").disabled = busy;
    $$(".preset, .identity-section input").forEach((el) => { el.disabled = busy || active; });
    $("#messageCount").textContent = `${count} B`;
    $("#messageCount").style.color = count > limit ? "var(--error)" : "";
    $("#messageLimit").textContent = limit ? `上限 ${bytes(limit)}` : "";
    $("#workspace").setAttribute("aria-busy", String(busy));
    $("#routeSender").textContent = state.session?.identities.sender || $("#senderName").value || "发送者";
    $("#routeReceiver").textContent = state.session?.identities.receiver || $("#receiverName").value || "接收者";
    $("#sessionStatus").textContent = active ? "会话已就绪" : "未开始";
    $("#cipherStatus").textContent = dirty ? "消息已修改，请重新加密" : cipher ? "密文已生成" : "尚未生成密文";
  }

  function renderSelection() {
    const preset = state.presets.find((p) => p.id === state.selected);
    if (!preset) return;
    $$(".preset").forEach((el) => {
      const active = el.dataset.preset === state.selected;
      el.classList.toggle("active", active);
      el.setAttribute("aria-pressed", String(active));
    });
    $("#schemeCaption").textContent = `方案 ${preset.code} / ${preset.title}`;
    $("#waitNote").hidden = !preset.wait_note;
    $("#waitNote").textContent = preset.wait_note || "";
    if (preset.group === "extra") $("#extras").open = true;
    try { sessionStorage.setItem("ibme-preset", state.selected); } catch (_) { /* storage is optional */ }
  }

  function renderPresets() {
    $("#presets").replaceChildren();
    $("#extraPresets").replaceChildren();
    for (const preset of state.presets) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "preset";
      button.dataset.preset = preset.id;
      button.setAttribute("aria-pressed", "false");
      const names = document.createElement("span");
      names.append(text("span", preset.title, "preset-title"), text("span", preset.note, "preset-note"));
      button.append(text("span", preset.code, "preset-letter"), names);
      button.addEventListener("click", async () => {
        state.selected = preset.id;
        state.ready = false;
        state.config = null;
        state.configJSON = null;
        state.capacity = {};
        renderSelection();
        await check();
      });
      $(preset.group === "main" ? "#presets" : "#extraPresets").append(button);
    }
    renderSelection();
    refreshControls();
  }

  function renderParameters() {
    const s = state.session;
    const cap = state.capacity;
    const items = [
      ["HIBE", state.config?.hibe || "—"], ["IBS", state.config?.ibs || "—"],
      ["身份上限", bytes(cap.identity_bytes)], ["消息上限", bytes(cap.max_application_bytes)],
      ["公共参数", bytes(s?.sizes.mpk)], ["主密钥", bytes(s?.sizes.msk)],
      ["发送者密钥", bytes(s?.sizes.sender_key)], ["接收者密钥", bytes(s?.sizes.receiver_key)],
      ["初始化", seconds(s?.timings.setup)], ["发送者发钥", seconds(s?.timings.sender_key)],
      ["接收者发钥", seconds(s?.timings.receiver_key)], ["测试身份发钥", seconds(s?.timings.wrong_receiver_key)],
    ];
    $("#parameterGrid").replaceChildren(...items.map(([name, value]) => {
      const row = document.createElement("div");
      row.append(text("dt", name), text("dd", value));
      return row;
    }));
    // Keep the server's decimal integers intact; JS Number rounds large parameters.
    $("#rawParameters").textContent = state.configJSON || "尚未读取配置。";
    $("#metricCipher").textContent = bytes(s?.sizes.ciphertext);
    $("#metricEncrypt").textContent = seconds(s?.timings.encrypt);
    $("#metricDecrypt").textContent = seconds(state.decrypt?.seconds);
    $("#cipherDigest").textContent = s?.ciphertext_sha256 ? `SHA-256 ${s.ciphertext_sha256.slice(0, 16)}…` : "";
  }

  function emptyResult(message) {
    $("#resultContent").replaceChildren(text("p", message, "empty-state"));
    $("#resultLabel").textContent = "";
    $("#resultLabel").className = "result-label";
  }

  function applySession(session, restoreMessage = false) {
    state.session = session;
    if (session) {
      state.ready = true;
      state.config = session.parameters;
      state.configJSON = session.parameters_json;
      state.capacity = session.capacity;
      const match = state.presets.find((p) => p.hibe === session.suite.hibe && p.ibs === session.suite.ibs && p.signature_format === session.suite.signature_format);
      if (match) state.selected = match.id;
      $("#senderName").value = session.identities.sender;
      $("#receiverName").value = session.identities.receiver;
      $("#wrongName").value = session.identities.wrong_receiver;
      if (restoreMessage && session.last_message !== null) $("#message").value = session.last_message;
      $("#checkStatus").textContent = "参数与身份已固定";
      $("#checkStatus").className = "check-status";
    } else {
      state.decrypt = null;
      state.receipt = null;
      state.receiptJSON = null;
      state.ready = false;
      state.config = null;
      state.configJSON = null;
      state.capacity = {};
      emptyResult("开始演示，加密一条消息。");
      renderRecords();
    }
    renderSelection();
    renderParameters();
    refreshControls();
  }

  function renderDecrypt(result) {
    state.decrypt = result;
    $("#testMode").value = result.mode;
    const label = $("#resultLabel");
    label.textContent = result.expectation_met ? "符合预期" : "结果异常";
    label.className = `result-label ${result.expectation_met ? "success" : "error"}`;
    const content = $("#resultContent");
    content.replaceChildren();
    if (result.bottom) {
      content.append(text("p", "拒绝解密", "rejected-title"), text("p", modeNames[result.mode], "result-detail"));
    } else {
      content.append(text("pre", result.message, "result-message"));
    }
    content.append(text("p", `接收者 ${result.receiver} · 声称发送者 ${result.claimed_sender}`, "result-detail"));
    renderParameters();
  }

  async function waitForJob(job) {
    $("#jobStatus").hidden = job.operation === "check";
    while (job.status === "queued" || job.status === "running") {
      $("#jobPhase").textContent = job.phase;
      $("#jobElapsed").textContent = seconds(job.elapsed);
      await delay(500);
      const latest = (await api("/api/jobs")).job;
      if (!latest || latest.id !== job.id) throw new ConnectionError("操作记录已变化，请重新连接查看会话。");
      job = latest;
    }
    $("#jobStatus").hidden = true;
    if (job.status === "failed") throw new Error(job.error || "操作未完成");
    return { operation: job.operation, result: job.result };
  }

  function acceptResult(operation, result) {
    if (operation === "check") {
      state.ready = result.ok;
      state.config = result.suite_config;
      state.configJSON = result.suite_config_json;
      state.capacity = result.capacity || {};
      $("#checkStatus").textContent = result.ok ? "配置就绪" : "运行环境未就绪";
      $("#checkStatus").className = `check-status${result.ok ? "" : " error"}`;
      if (!result.ok) showError(new Error((result.errors || []).join("；")));
      renderParameters();
    } else if (operation === "reset") {
      state.session = null;
      state.decrypt = null;
      state.receipt = null;
      state.receiptJSON = null;
      state.ready = false;
      $("#testMode").value = "normal";
      emptyResult("开始演示，加密一条消息。");
      renderParameters();
      renderRecords();
    } else {
      if (result.state) applySession(result.state);
      if (operation === "decrypt") renderDecrypt(result);
      else {
        state.decrypt = null;
        emptyResult(operation === "encrypt" ? "选择验证情形，尝试解密。" : "输入消息，点击加密。");
        renderParameters();
      }
      state.receipt = null;
      state.receiptJSON = null;
    }
  }

  async function operation(name, payload) {
    if (state.busy || state.uncertain) return;
    clearError();
    state.busy = true;
    refreshControls();
    try {
      const submitted = (await api("/api/jobs", { operation: name, payload })).job;
      const done = await waitForJob(submitted);
      acceptResult(done.operation, done.result);
    } catch (error) {
      showError(error);
      if (name === "check") {
        state.ready = false;
        $("#checkStatus").textContent = "配置检查未完成";
        $("#checkStatus").className = "check-status error";
      }
      if (name === "decrypt") {
        state.decrypt = null;
        emptyResult("解密未完成。");
        renderParameters();
      }
    } finally {
      if (!state.uncertain) $("#jobStatus").hidden = true;
      state.busy = false;
      refreshControls();
    }
    if (!$("#recordsView").hidden) await loadReceipt();
  }

  async function check() {
    $("#checkStatus").textContent = "检查配置中…";
    await operation("check", { preset: state.selected });
  }

  function renderRecords() {
    const receipt = state.receipt;
    const rows = [];
    const phases = { build: "准备运行环境", setup: "初始化公共参数", sender_key: "发送者发钥", receiver_key: "接收者发钥", wrong_receiver_key: "测试身份发钥" };
    for (const [key, label] of Object.entries(phases)) {
      if (Number.isFinite(receipt?.timings[key])) rows.push([label, "—", seconds(receipt.timings[key]), "完成"]);
    }
    for (const item of receipt?.observations || []) {
      rows.push([
        item.operation === "encrypt" ? "加密" : "解密", modeNames[item.mode] || "—", seconds(item.seconds),
        item.operation === "encrypt" ? "已生成密文" : !item.expectation_met ? "结果异常" : item.bottom ? "拒绝解密" : "恢复原文",
      ]);
    }
    const body = $("#recordsBody");
    body.replaceChildren();
    if (!rows.length) {
      const row = document.createElement("tr");
      const cell = text("td", state.session ? "切换到此页时读取运行记录。" : "开始演示后，这里会记录每次操作。", "empty-records");
      cell.colSpan = 4;
      row.append(cell);
      body.append(row);
    }
    for (const values of rows) {
      const row = document.createElement("tr");
      for (const value of values) row.append(text("td", value, value === "结果异常" ? "record-error" : ""));
      body.append(row);
    }
  }

  async function loadReceipt() {
    if (!state.session || state.busy || state.uncertain) return;
    state.busy = true;
    state.receipt = null;
    state.receiptJSON = null;
    refreshControls();
    try {
      state.receiptJSON = await api("/api/export", undefined, true);
      state.receipt = JSON.parse(state.receiptJSON);
      renderRecords();
    } catch (error) { showError(error); }
    finally { state.busy = false; refreshControls(); }
  }

  async function connect() {
    state.busy = true;
    state.uncertain = false;
    clearError();
    refreshControls();
    try {
      const [catalog, pending] = await Promise.all([api("/api/backends"), api("/api/jobs")]);
      state.presets = catalog.presets;
      try { state.selected = sessionStorage.getItem("ibme-preset") || "primary"; } catch (_) { /* optional */ }
      if (!state.presets.some((p) => p.id === state.selected)) state.selected = "primary";
      renderPresets();
      if (pending.job && ["queued", "running"].includes(pending.job.status)) {
        const done = await waitForJob(pending.job);
        acceptResult(done.operation, done.result);
      }
      const response = await api("/api/state");
      applySession(response.active ? response.state : null, true);
      if (state.session && !state.decrypt) emptyResult(state.session.has_ciphertext ? "密文已恢复，可继续解密验证。" : "输入消息，点击加密。");
    } catch (error) {
      showError(error);
    } finally {
      state.busy = false;
      refreshControls();
    }
    if (!state.uncertain && !state.session && state.presets.length) await check();
  }

  $("#startBtn").addEventListener("click", () => operation("bootstrap", {
    preset: state.selected, sender: $("#senderName").value,
    receiver: $("#receiverName").value, wrong_receiver: $("#wrongName").value,
  }));
  $("#encryptBtn").addEventListener("click", () => operation("encrypt", { message: $("#message").value }));
  $("#decryptBtn").addEventListener("click", () => operation("decrypt", { mode: $("#testMode").value }));
  $("#resetBtn").addEventListener("click", async () => {
    await operation("reset", {});
    if (!state.session && !state.uncertain) await check();
  });
  $("#testMode").addEventListener("change", () => emptyResult("点击解密验证，查看本次结果。"));
  $("#message").addEventListener("input", () => {
    if (state.session?.has_ciphertext) {
      state.decrypt = null;
      const dirty = $("#message").value !== state.session.last_message;
      emptyResult(dirty ? "消息已修改，请重新加密。" : "消息与现有密文一致，可继续解密验证。");
      renderParameters();
    }
    refreshControls();
  });
  ["#senderName", "#receiverName"].forEach((id) => $(id).addEventListener("input", refreshControls));
  $("#dismissError").addEventListener("click", () => { if (!state.uncertain) clearError(); });
  $("#reconnectBtn").addEventListener("click", connect);
  $$(".tab").forEach((button) => button.addEventListener("click", async () => {
    const records = button.dataset.view === "records";
    $("#demoView").hidden = records;
    $("#recordsView").hidden = !records;
    $$(".tab").forEach((tab) => {
      tab.classList.toggle("active", tab === button);
      tab.setAttribute("aria-pressed", String(tab === button));
    });
    if (records) { renderRecords(); await loadReceipt(); }
  }));
  $("#exportBtn").addEventListener("click", async () => {
    await loadReceipt();
    if (!state.receiptJSON || state.busy || state.uncertain) return;
    const url = URL.createObjectURL(new Blob([state.receiptJSON], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "ibme-demo-measurements.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  refreshControls();
  connect();
})();
