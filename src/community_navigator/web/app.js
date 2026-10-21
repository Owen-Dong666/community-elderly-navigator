"use strict";

let currentSessionId = null;
let requestPending = false;
let canNavigate = false;

const queryForm = document.querySelector("#query-form");
const queryInput = document.querySelector("#query-input");
const submitButton = document.querySelector("#submit-button");
const voiceButton = document.querySelector("#voice-button");
const systemMessage = document.querySelector("#system-message");
const deviceButtons = [...document.querySelectorAll("[data-action]")];

function setPending(pending) {
  requestPending = pending;
  submitButton.disabled = pending;
  voiceButton.disabled = pending;
  deviceButtons.forEach((button) => {
    button.disabled = pending || !currentSessionId || !canNavigate;
  });
}

function setMessage(message, isError = false) {
  systemMessage.textContent = message;
  systemMessage.classList.toggle("is-error", isError);
}

async function submitQuery(text) {
  const query = text.trim();
  if (!query || requestPending) {
    if (!query) setMessage("请先说出或输入要办理的事情", true);
    return;
  }

  setPending(true);
  setMessage("正在查询社区资料……");
  try {
    const response = await fetch("/api/v1/query", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: query}),
    });
    if (!response.ok) throw new Error("查询请求失败");
    const state = await response.json();
    currentSessionId = state.session_id;
    renderDeviceState(state);
    setMessage(state.status === "ready" ? "已找到服务，请按屏幕提示办理" : "请留意屏幕上的确认提示");
  } catch (error) {
    currentSessionId = null;
    canNavigate = false;
    setMessage("暂时无法连接电脑端，请确认程序已经启动", true);
  } finally {
    setPending(false);
  }
}

async function sendButton(type) {
  if (!currentSessionId || requestPending) return;
  setPending(true);
  setMessage(type === "BUTTON_A" ? "正在重复当前步骤……" : "正在切换下一步骤……");
  try {
    const response = await fetch(`/api/v1/sessions/${encodeURIComponent(currentSessionId)}/events`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({type}),
    });
    if (!response.ok) throw new Error("按键请求失败");
    const state = await response.json();
    renderDeviceState(state);
    if (state.ended) {
      currentSessionId = null;
      setMessage("本次导航完成，可以开始新的查询");
    } else {
      setMessage(type === "BUTTON_A" ? "已重复播报" : "已切换步骤");
    }
  } catch (error) {
    setMessage("按键响应失败，请稍后再试", true);
  } finally {
    setPending(false);
  }
}

function renderDeviceState(state) {
  const device = state.device;
  canNavigate = state.status === "ready" && !state.ended;
  document.querySelector("#screen-service").textContent = device.service_name || "等待查询";
  document.querySelector("#screen-title").textContent = device.title;
  document.querySelector("#screen-body").textContent = device.body || "请查看提示";
  document.querySelector("#screen-helper").textContent = device.helper_text;
  document.querySelector("#screen-progress").textContent = device.current_step_index === null
    ? "— / —"
    : `${device.current_step_index + 1} / ${device.total_steps}`;

  const active = new Set(device.active_leds);
  document.querySelectorAll("[data-led-index]").forEach((led) => {
    const ledIndex = Number(led.dataset.ledIndex);
    led.classList.toggle("is-active", active.has(ledIndex));
  });
  document.querySelector("#map-status").textContent = active.size
    ? `已点亮 ${[...active].join("、")} 号地点指示灯`
    : "地图指示灯已关闭";

  const shouldSpeak = Boolean(device.speech_text && device.speech_status === "queued");
  document.querySelector("#speaker-status").textContent = shouldSpeak
    ? `扬声器：${device.speech_text}`
    : "扬声器：等待播报";
  if (shouldSpeak) speak(device.speech_text);

  deviceButtons.forEach((button) => {
    button.disabled = requestPending || !currentSessionId || !canNavigate;
  });
}

function speak(text) {
  if (!("speechSynthesis" in window)) {
    document.querySelector("#speaker-status").textContent = "扬声器：此浏览器不支持语音播报";
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}

function startVoiceInput() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    setMessage("当前浏览器不支持语音识别，请使用文字输入", true);
    queryInput.focus();
    return;
  }
  const recognition = new Recognition();
  recognition.lang = "zh-CN";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  voiceButton.classList.add("is-listening");
  voiceButton.querySelector("span:last-child").textContent = "正在聆听";
  setMessage("请说出您想办理的事情……");
  recognition.addEventListener("result", (event) => {
    const text = event.results[0][0].transcript;
    queryInput.value = text;
    submitQuery(text);
  });
  recognition.addEventListener("error", () => {
    setMessage("没有听清楚，请再试一次或使用文字输入", true);
  });
  recognition.addEventListener("end", () => {
    voiceButton.classList.remove("is-listening");
    voiceButton.querySelector("span:last-child").textContent = "语音输入";
  });
  recognition.start();
}

queryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuery(queryInput.value);
});
voiceButton.addEventListener("click", startVoiceInput);
deviceButtons.forEach((button) => {
  button.addEventListener("click", () => sendButton(button.dataset.action));
});
document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.query;
    submitQuery(button.dataset.query);
  });
});

setPending(false);
