"use strict";

const DEFAULTS = {
  baseUrl: "https://reader.example.com",
  importToken: "",
  voice: "zh-CN-XiaoxiaoNeural",
  readerMode: "assistant"
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "POCKETREADER_CAPTURE_SUBMIT") {
    return false;
  }

  submitCapture(message.payload)
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
  return true;
});

async function submitCapture(payload) {
  const settings = await chrome.storage.sync.get(DEFAULTS);
  const baseUrl = String(settings.baseUrl || DEFAULTS.baseUrl).replace(/\/+$/, "");
  const importToken = String(settings.importToken || "");
  if (!importToken) {
    throw new Error("请先在扩展设置里填写 IMPORT_TOKEN。");
  }

  const body = {
    ...payload,
    voice: payload.voice || settings.voice || DEFAULTS.voice,
    reader_mode: payload.reader_mode || settings.readerMode || DEFAULTS.readerMode
  };

  const response = await fetch(`${baseUrl}/api/browser-capture`, {
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
