"use strict";

const SETTINGS_VERSION = 2;
const DEFAULTS = {
  baseUrl: "https://reader.example.com",
  importToken: "",
  voice: "zh-CN-XiaoxiaoNeural",
  readerMode: "all",
  splitByTurn: false
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message) {
    return false;
  }

  if (message.type === "POCKETREADER_OPEN_OPTIONS") {
    openOptionsPage()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }

  if (message.type === "POCKETREADER_CAPTURE_SUBMIT") {
    submitCapture(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }

  if (message.type === "POCKETREADER_SNAPSHOT_PARSE") {
    parseSnapshot(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }

  if (message.type === "POCKETREADER_SNAPSHOT_CREATE") {
    createSnapshotItems(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }

  return false;
});

async function submitCapture(payload) {
  const body = await payloadWithSettings(payload);
  return postPocketReader("/api/browser-capture", body);
}

async function parseSnapshot(payload) {
  const settings = await requireSettings();
  const body = {
    ...payload,
    extension_version: chrome.runtime.getManifest().version
  };
  return postPocketReader("/api/browser-snapshot", body, settings);
}

async function createSnapshotItems(payload) {
  const body = await payloadWithSettings(payload);
  const captureId = Number(body.capture_id || 0);
  if (!captureId) {
    throw new Error("缺少 capture_id，请重新打开导入面板。");
  }
  return postPocketReader(`/api/browser-snapshot/${captureId}/create`, body);
}

async function payloadWithSettings(payload) {
  const settings = await chrome.storage.sync.get(DEFAULTS);
  const readerMode =
    Number(settings.settingsVersion || 0) < SETTINGS_VERSION
      ? DEFAULTS.readerMode
      : settings.readerMode || DEFAULTS.readerMode;

  return {
    ...payload,
    voice: payload.voice || settings.voice || DEFAULTS.voice,
    reader_mode: payload.reader_mode || readerMode,
    split_by_turn: Boolean(payload.split_by_turn ?? settings.splitByTurn ?? DEFAULTS.splitByTurn),
    include_user_question:
      payload.include_user_question ?? ((payload.reader_mode || readerMode) !== "assistant")
  };
}

async function requireSettings() {
  const settings = await chrome.storage.sync.get(DEFAULTS);
  const importToken = String(settings.importToken || "");
  if (!importToken) {
    await openOptionsPage();
    throw new Error("请在打开的扩展设置页填写 IMPORT_TOKEN，然后回到这里重新提交。");
  }
  return settings;
}

async function postPocketReader(path, body, providedSettings = null) {
  const settings = providedSettings || (await requireSettings());
  const baseUrl = String(settings.baseUrl || DEFAULTS.baseUrl).replace(/\/+$/, "");
  const importToken = String(settings.importToken || "");
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-PocketReader-Import-Token": importToken
    },
    body: JSON.stringify(body)
  });

  let data = null;
  try {
    data = await response.json();
  } catch (_error) {
    data = null;
  }

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `HTTP ${response.status}`;
    throw new Error(`导入失败：${detail}`);
  }
  return data;
}

function openOptionsPage() {
  return new Promise((resolve, reject) => {
    if (typeof chrome.runtime.openOptionsPage === "function") {
      chrome.runtime.openOptionsPage(() => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(error.message));
          return;
        }
        resolve();
      });
      return;
    }

    chrome.tabs.create({ url: chrome.runtime.getURL("options.html") }, () => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      resolve();
    });
  });
}
