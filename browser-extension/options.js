"use strict";

const SETTINGS_VERSION = 2;
const DEFAULTS = {
  baseUrl: "http://127.0.0.1:4780",
  importToken: "",
  voice: "zh-CN-XiaoxiaoNeural",
  readerMode: "all",
  splitByTurn: true
};

const form = document.querySelector("#settings-form");
const statusNode = document.querySelector("#status");

restore();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const settings = {
    baseUrl: document.querySelector("#base-url").value.trim().replace(/\/+$/, ""),
    importToken: document.querySelector("#import-token").value.trim(),
    voice: document.querySelector("#voice").value,
    readerMode: document.querySelector("#reader-mode").value,
    splitByTurn: document.querySelector("#split-by-turn").checked,
    settingsVersion: SETTINGS_VERSION
  };
  try {
    const url = new URL(settings.baseUrl);
    if (url.username || url.password || url.search || url.hash || url.pathname !== "/") {
      throw new Error("请填写服务根地址，不要包含路径、查询参数或登录凭证。");
    }
    if (url.protocol !== "https:" && url.origin !== DEFAULTS.baseUrl) {
      throw new Error("远程服务请使用 HTTPS；本地开发请使用 http://127.0.0.1:4780。");
    }
    settings.baseUrl = url.origin;
    // Request only the configured origin, directly from this Save button gesture.
    const granted = await chrome.permissions.request({ origins: [`${url.origin}/*`] });
    if (!granted) {
      throw new Error("尚未允许访问此服务地址，设置未保存。");
    }
    await chrome.storage.sync.set(settings);
  } catch (error) {
    statusNode.textContent = error.message || "设置保存失败";
    return;
  }
  statusNode.textContent = "已保存";
  window.setTimeout(() => {
    statusNode.textContent = "";
  }, 1800);
});

async function restore() {
  const settings = await chrome.storage.sync.get(DEFAULTS);
  document.querySelector("#base-url").value = settings.baseUrl || DEFAULTS.baseUrl;
  document.querySelector("#import-token").value = settings.importToken || "";
  document.querySelector("#voice").value = settings.voice || DEFAULTS.voice;
  document.querySelector("#reader-mode").value =
    Number(settings.settingsVersion || 0) < SETTINGS_VERSION
      ? DEFAULTS.readerMode
      : settings.readerMode || DEFAULTS.readerMode;
  document.querySelector("#split-by-turn").checked = Boolean(
    settings.splitByTurn || DEFAULTS.splitByTurn
  );
}
