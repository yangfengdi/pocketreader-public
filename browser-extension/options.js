"use strict";

const SETTINGS_VERSION = 2;
const DEFAULTS = {
  baseUrl: "https://reader.example.com",
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
  await chrome.storage.sync.set(settings);
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
