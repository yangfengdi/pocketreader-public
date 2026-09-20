"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const source = fs.readFileSync(path.join(__dirname, "../browser-extension/options.js"), "utf8");

async function saveSettings(baseUrl, permissionGranted) {
  const nodes = new Map();
  let submit;
  let saved;
  const requests = [];
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, { value: "", checked: true, textContent: "" });
    return nodes.get(id);
  };
  node("#settings-form").addEventListener = (_event, fn) => { submit = fn; };
  const context = {
    URL,
    document: { querySelector: node },
    window: { setTimeout() {} },
    chrome: {
      storage: { sync: { get: async (defaults) => ({ ...defaults }), set: async (settings) => { saved = settings; } } },
      permissions: { request: async (request) => { requests.push(request); return permissionGranted; } }
    }
  };
  vm.runInNewContext(source, context);
  await Promise.resolve();
  node("#base-url").value = baseUrl;
  node("#import-token").value = "test-import-token";
  await submit({ preventDefault() {} });
  return { saved, requests, status: node("#status").textContent };
}

(async () => {
  let result = await saveSettings("https://reader.example.com/", true);
  assert.equal(result.saved.baseUrl, "https://reader.example.com");
  assert.equal(result.requests[0].origins[0], "https://reader.example.com/*");
  result = await saveSettings("https://reader.example.com", false);
  assert.equal(result.saved, undefined);
  assert.match(result.status, /设置未保存/);
  result = await saveSettings("http://reader.example.com", true);
  assert.equal(result.saved, undefined);
  assert.equal(result.requests.length, 0);
  result = await saveSettings("https://reader.example.com/path", true);
  assert.equal(result.saved, undefined);
  result = await saveSettings("http://127.0.0.1:4780", true);
  assert.equal(result.saved.baseUrl, "http://127.0.0.1:4780");
  console.log("ok - settings authorize only the chosen origin, reject unsafe URLs and preserve settings on denial");
})().catch((error) => { console.error(error); process.exitCode = 1; });
