"use strict";

const POCKETREADER_MAX_FILE_TEXT_CHARS = 300000;
const POCKETREADER_MAX_BINARY_FILE_BYTES = 4 * 1024 * 1024;
const POCKETREADER_TEXT_FILE_EXTENSIONS = new Set([
  "txt",
  "md",
  "markdown",
  "csv",
  "tsv",
  "json",
  "jsonl",
  "yaml",
  "yml",
  "xml",
  "html",
  "htm",
  "rtf",
  "log",
  "py",
  "js",
  "ts",
  "tsx",
  "jsx",
  "css",
  "scss",
  "sql",
  "sh",
  "bash",
  "zsh",
  "toml",
  "ini",
  "conf",
  "tex"
]);
const POCKETREADER_BINARY_DOCUMENT_EXTENSIONS = new Set(["docx"]);

(function initPocketReaderCapture() {
  if (document.querySelector("#pocketreader-capture-root")) {
    return;
  }

  const SETTINGS_VERSION = 2;
  const DEFAULTS = {
    voice: "zh-CN-XiaoxiaoNeural",
    readerMode: "all",
    splitByTurn: false
  };

  const VOICES = [
    ["zh-CN-XiaoxiaoNeural", "中文女声 - Xiaoxiao"],
    ["zh-CN-XiaoyiNeural", "中文女声 - Xiaoyi"],
    ["zh-CN-YunxiNeural", "中文男声 - Yunxi"],
    ["zh-CN-YunjianNeural", "中文男声 - Yunjian"],
    ["zh-TW-HsiaoChenNeural", "台湾中文女声 - HsiaoChen"],
    ["en-US-EmmaMultilingualNeural", "中英混合女声 - Emma"],
    ["en-US-AriaNeural", "英文女声 - Aria"],
    ["en-US-GuyNeural", "英文男声 - Guy"]
  ];

  const root = document.createElement("div");
  root.id = "pocketreader-capture-root";
  root.innerHTML = `
    <div class="pocketreader-panel" aria-live="polite">
      <div class="pocketreader-panel-header">
        <span>导入 PocketReader</span>
        <button type="button" class="pocketreader-panel-close" aria-label="关闭">×</button>
      </div>
      <div class="pocketreader-panel-body">
        <label>
          标题
          <input type="text" data-pocketreader-title>
        </label>
        <label>
          朗读范围
          <select data-pocketreader-reader-mode>
            <option value="all">问题和 AI 回复</option>
            <option value="assistant">只读 AI 回复</option>
          </select>
        </label>
        <label class="pocketreader-checkbox">
          <input type="checkbox" data-pocketreader-split-turns>
          <span>每个回合生成一个独立音频</span>
        </label>
        <label>
          声音
          <select data-pocketreader-voice></select>
        </label>
        <button type="button" class="pocketreader-submit">提交导入</button>
        <button type="button" class="pocketreader-secondary">扩展设置</button>
        <div class="pocketreader-status"></div>
      </div>
    </div>
    <button type="button" class="pocketreader-capture-button">导入 PocketReader</button>
  `;
  document.body.append(root);

  const panel = root.querySelector(".pocketreader-panel");
  const openButton = root.querySelector(".pocketreader-capture-button");
  const closeButton = root.querySelector(".pocketreader-panel-close");
  const submitButton = root.querySelector(".pocketreader-submit");
  const optionsButton = root.querySelector(".pocketreader-secondary");
  const titleInput = root.querySelector("[data-pocketreader-title]");
  const readerModeSelect = root.querySelector("[data-pocketreader-reader-mode]");
  const splitTurnsInput = root.querySelector("[data-pocketreader-split-turns]");
  const voiceSelect = root.querySelector("[data-pocketreader-voice]");
  const statusNode = root.querySelector(".pocketreader-status");

  for (const [value, label] of VOICES) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    voiceSelect.append(option);
  }

  loadSettings()
    .then((settings) => {
      voiceSelect.value = settings.voice || DEFAULTS.voice;
      readerModeSelect.value =
        Number(settings.settingsVersion || 0) < SETTINGS_VERSION
          ? DEFAULTS.readerMode
          : settings.readerMode || DEFAULTS.readerMode;
      splitTurnsInput.checked = Boolean(settings.splitByTurn || DEFAULTS.splitByTurn);
    })
    .catch((error) => {
      showStatus(extensionErrorMessage(error), "error");
    });

  openButton.addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) {
      const capture = captureConversation();
      titleInput.value = capture.title;
      showStatus(
        recognitionMessage(capture.messages.length, capture.file_count),
        capture.messages.length || capture.file_count ? "" : "error"
      );
    }
  });

  closeButton.addEventListener("click", () => {
    panel.classList.remove("open");
  });

  optionsButton.addEventListener("click", () => {
    openOptionsPage().catch((error) => {
      showStatus(error.message || String(error), "error");
    });
  });

  submitButton.addEventListener("click", async () => {
    const capture = await captureConversationWithFiles();
    capture.title = titleInput.value.trim() || capture.title;
    capture.voice = voiceSelect.value;
    capture.reader_mode = readerModeSelect.value;
    capture.split_by_turn = splitTurnsInput.checked;
    capture.include_user_question = readerModeSelect.value !== "assistant";

    if (!capture.messages.length && !capture.files.length) {
      showStatus("没有识别到可导入的对话文本或文本文件。", "error");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "提交中";
    showStatus("正在提交到 PocketReader", "");
    try {
      const response = await sendRuntimeMessage({
        type: "POCKETREADER_CAPTURE_SUBMIT",
        payload: capture
      });
      if (!response || !response.ok) {
        throw new Error(response && response.error ? response.error : "提交失败");
      }
      const result = response.result || {};
      if (Array.isArray(result.item_ids) && result.item_ids.length > 1) {
        showStatus(`已创建 ${result.item_ids.length} 个条目`, "ok");
      } else {
        const itemId = result.item_id || (Array.isArray(result.item_ids) ? result.item_ids[0] : "");
        showStatus(`已创建条目 #${itemId}`, "ok");
      }
    } catch (error) {
      showStatus(extensionErrorMessage(error), "error");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "提交导入";
    }
  });

  function showStatus(message, state) {
    statusNode.textContent = message;
    statusNode.classList.toggle("ok", state === "ok");
    statusNode.classList.toggle("error", state === "error");
  }

  async function openOptionsPage() {
    try {
      const response = await sendRuntimeMessage({
        type: "POCKETREADER_OPEN_OPTIONS"
      });
      if (!response || !response.ok) {
        throw new Error(response && response.error ? response.error : "无法打开扩展设置。");
      }
    } catch (error) {
      if (isExtensionContextInvalidated(error)) {
        throw error;
      }
      window.open(runtimeUrl("options.html"), "_blank");
    }
  }

  async function loadSettings() {
    if (!isRuntimeAvailable()) {
      throw new Error("Extension context invalidated.");
    }
    return chrome.storage.sync.get(DEFAULTS);
  }

  async function sendRuntimeMessage(message) {
    if (!isRuntimeAvailable()) {
      throw new Error("Extension context invalidated.");
    }
    return chrome.runtime.sendMessage(message);
  }

  function runtimeUrl(path) {
    if (!isRuntimeAvailable()) {
      throw new Error("Extension context invalidated.");
    }
    return chrome.runtime.getURL(path);
  }
})();

function captureConversation() {
  const platform = platformFromHost(location.hostname);
  const messages = cleanMessages(extractMessages(platform));
  const fileCount = collectGeneratedFileCandidates(platform).length;
  return {
    platform,
    url: location.href,
    title: titleFromPage(platform, messages),
    messages,
    files: [],
    file_count: fileCount
  };
}

async function captureConversationWithFiles() {
  const capture = captureConversation();
  capture.files = await extractGeneratedFiles(capture.platform);
  capture.file_count = capture.files.length;
  return capture;
}

function platformFromHost(host) {
  if (host.includes("gemini.google.com")) {
    return "gemini";
  }
  if (host.includes("claude.ai")) {
    return "claude";
  }
  return "chatgpt";
}

function extractMessages(platform) {
  if (platform === "chatgpt") {
    return extractChatGPTMessages();
  }
  if (platform === "gemini") {
    return extractGeminiMessages();
  }
  if (platform === "claude") {
    return extractClaudeMessages();
  }
  return [];
}

function extractChatGPTMessages() {
  const nodes = Array.from(document.querySelectorAll("[data-message-author-role]"));
  if (nodes.length) {
    return nodes.map((node) => ({
      node,
      role: node.getAttribute("data-message-author-role"),
      text: textFromNode(readableChild(node) || node)
    }));
  }

  return collectCandidates([
    ["User", "[data-testid*='user-message'], .font-user-message"],
    ["AI", "[data-testid*='assistant-message'], .markdown.prose, .markdown"]
  ]);
}

function extractGeminiMessages() {
  return collectCandidates([
    ["User", "user-query, [data-test-id='user-query'], [data-testid='user-query'], .query-text"],
    [
      "AI",
      "model-response, [data-test-id='model-response'], [data-testid='model-response'], .model-response-text, .response-container, message-content"
    ]
  ]);
}

function extractClaudeMessages() {
  return collectCandidates([
    ["User", "[data-testid='user-message'], [data-testid*='user-message'], .font-user-message"],
    [
      "AI",
      "[data-testid='assistant-message'], [data-testid*='assistant-message'], .font-claude-message, [data-is-streaming], .markdown.prose"
    ]
  ]);
}

function collectCandidates(roleSelectors) {
  let candidates = [];
  for (const [role, selectors] of roleSelectors) {
    for (const node of document.querySelectorAll(selectors)) {
      candidates = addCandidate(candidates, role, node);
    }
  }
  return candidates.sort(compareNodeOrder).map((candidate) => ({
    role: candidate.role,
    text: textFromNode(readableChild(candidate.node) || candidate.node)
  }));
}

function addCandidate(candidates, role, node) {
  if (!isVisible(node)) {
    return candidates;
  }
  if (candidates.some((candidate) => candidate.role === role && candidate.node.contains(node))) {
    return candidates;
  }
  return candidates
    .filter((candidate) => !(candidate.role === role && node.contains(candidate.node)))
    .concat([{ role, node }]);
}

function compareNodeOrder(a, b) {
  if (a.node === b.node) {
    return 0;
  }
  return a.node.compareDocumentPosition(b.node) & Node.DOCUMENT_POSITION_PRECEDING ? 1 : -1;
}

function readableChild(node) {
  return (
    node.querySelector("[data-message-id] .markdown") ||
    node.querySelector("[data-message-id]") ||
    node.querySelector(".markdown.prose") ||
    node.querySelector(".markdown") ||
    node.querySelector(".model-response-text") ||
    node.querySelector("message-content") ||
    null
  );
}

function textFromNode(node) {
  const clone = node.cloneNode(true);
  for (const removable of clone.querySelectorAll(
    "button, svg, style, script, textarea, input, select, nav, menu, [aria-hidden='true'], [hidden]"
  )) {
    removable.remove();
  }
  return cleanText(clone.innerText || clone.textContent || "");
}

async function extractGeneratedFiles(platform) {
  const candidates = collectGeneratedFileCandidates(platform);
  const files = [];
  const seen = new Set();
  for (const candidate of candidates) {
    const file = await readGeneratedFile(candidate);
    if (!file || !file.body) {
      continue;
    }
    const key = `${file.filename || file.title}\n${file.body}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    files.push(file);
  }
  return files;
}

function collectGeneratedFileCandidates(platform) {
  const candidates = [];
  const scopes = fileSearchScopes(platform);
  for (const scope of scopes) {
    for (const node of scope.querySelectorAll("a[download], a[href], [data-testid], [aria-label], [title]")) {
      addFileCandidate(candidates, node);
    }
  }
  return candidates;
}

function fileSearchScopes(platform) {
  const selectors = [
    "[data-message-author-role='assistant']",
    "[data-testid*='assistant-message']",
    ".font-claude-message",
    "[data-is-streaming]",
    "model-response",
    "[data-test-id='model-response']",
    "[data-testid='model-response']",
    ".model-response-text",
    ".response-container",
    "message-content"
  ];
  if (platform === "claude") {
    selectors.push("[data-testid*='artifact']", "[class*='artifact']");
  }
  const scopes = Array.from(document.querySelectorAll(selectors.join(","))).filter(isVisible);
  return scopes.length ? scopes : [document.body];
}

function addFileCandidate(candidates, node) {
  if (!isVisible(node)) {
    return;
  }
  const filename = fileNameFromNode(node);
  if (!filename || (!isLikelyTextFile(filename) && !isSupportedBinaryDocument(filename))) {
    return;
  }
  const href = hrefFromNode(node);
  const key = `${filename}\n${href || cleanText(node.textContent || "").slice(0, 200)}`;
  if (candidates.some((candidate) => candidate.key === key)) {
    return;
  }
  candidates.push({
    key,
    node,
    title: filename,
    filename,
    url: href
  });
}

async function readGeneratedFile(candidate) {
  const inlineText = inlineFileText(candidate.node, candidate.filename);
  if (inlineText) {
    return {
      title: candidate.title,
      filename: candidate.filename,
      body: inlineText,
      url: candidate.url || null
    };
  }
  if (!candidate.url || !isFetchableUrl(candidate.url)) {
    return null;
  }
  try {
    const response = await fetch(candidate.url, { credentials: "include" });
    if (!response.ok) {
      return null;
    }
    const blob = await response.blob();
    const contentType = response.headers.get("content-type") || blob.type || "";
    if (isLikelyTextFile(candidate.filename) || isTextContentType(contentType)) {
      const text = cleanText(await blob.text()).slice(0, POCKETREADER_MAX_FILE_TEXT_CHARS);
      return text
        ? {
            title: candidate.title,
            filename: candidate.filename,
            body: text,
            content_type: contentType,
            url: candidate.url
          }
        : null;
    }
    if (
      isSupportedBinaryDocument(candidate.filename) &&
      blob.size <= POCKETREADER_MAX_BINARY_FILE_BYTES
    ) {
      return {
        title: candidate.title,
        filename: candidate.filename,
        data_base64: await blobToBase64(blob),
        content_type: contentType,
        url: candidate.url
      };
    }
  } catch (_error) {
    return null;
  }
  return null;
}

function inlineFileText(node, filename) {
  const contentNode = node.matches("pre, code, textarea")
    ? node
    : node.querySelector("pre, code, textarea, [contenteditable='true']");
  if (!contentNode) {
    return "";
  }
  const text = cleanText(contentNode.innerText || contentNode.textContent || "");
  if (!text || text === filename || text.length < 3) {
    return "";
  }
  return text.slice(0, POCKETREADER_MAX_FILE_TEXT_CHARS);
}

function fileNameFromNode(node) {
  const direct = [
    node.getAttribute("download"),
    node.getAttribute("title"),
    node.getAttribute("aria-label"),
    cleanText(node.textContent || "")
  ];
  const href = hrefFromNode(node);
  for (const value of direct) {
    const filename = matchFileName(value);
    if (filename) {
      return filename;
    }
  }
  const filenameFromHref = fileNameFromUrl(href);
  if (
    filenameFromHref &&
    (node.hasAttribute("download") ||
      looksLikeFileElement(node) ||
      cleanText(node.textContent || "").includes(filenameFromHref))
  ) {
    return filenameFromHref;
  }
  return "";
}

function looksLikeFileElement(node) {
  const attributes = [
    node.getAttribute("data-testid"),
    node.getAttribute("aria-label"),
    node.getAttribute("title"),
    node.getAttribute("class")
  ]
    .join(" ")
    .toLowerCase();
  return /file|download|attachment|artifact/.test(attributes);
}

function hrefFromNode(node) {
  const link = node.closest("a[href]") || node.querySelector("a[href]");
  return link ? link.href : "";
}

function matchFileName(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const match = text.match(
    /([\p{L}\p{N}][\p{L}\p{N}\s._()[\]-]{0,100}\.(txt|md|markdown|csv|tsv|json|jsonl|yaml|yml|xml|html|htm|rtf|log|py|js|ts|tsx|jsx|css|scss|sql|sh|bash|zsh|toml|ini|conf|tex|docx))/iu
  );
  return match ? match[1].trim() : "";
}

function fileNameFromUrl(url) {
  try {
    const parsed = new URL(url, location.href);
    for (const key of ["filename", "file", "name", "download"]) {
      const value = parsed.searchParams.get(key);
      if (value) {
        const filename = matchFileName(decodeURIComponent(value));
        if (filename) {
          return filename;
        }
      }
    }
    const path = decodeURIComponent(parsed.pathname.split("/").pop() || "");
    return path || "";
  } catch (_error) {
    return "";
  }
}

function isLikelyTextFile(filename) {
  const extension = fileExtension(filename);
  return POCKETREADER_TEXT_FILE_EXTENSIONS.has(extension);
}

function isSupportedBinaryDocument(filename) {
  const extension = fileExtension(filename);
  return POCKETREADER_BINARY_DOCUMENT_EXTENSIONS.has(extension);
}

function fileExtension(filename) {
  const match = String(filename || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : "";
}

function isFetchableUrl(url) {
  return /^(https?:|blob:)/i.test(url);
}

function isTextContentType(contentType) {
  const value = String(contentType || "").toLowerCase();
  return (
    value.startsWith("text/") ||
    value.includes("json") ||
    value.includes("xml") ||
    value.includes("yaml") ||
    value.includes("javascript")
  );
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",").pop() : result);
    };
    reader.onerror = () => reject(reader.error || new Error("FileReader failed."));
    reader.readAsDataURL(blob);
  });
}

function cleanMessages(messages) {
  const cleaned = [];
  const seen = new Set();
  for (const message of messages) {
    const role = normalizeRole(message.role);
    const text = cleanText(message.text).replace(/^(ChatGPT|Gemini|Claude|You|User|Assistant)\s*\n/i, "");
    if (!role || text.length < 2 || isMostlyUiText(text)) {
      continue;
    }
    const key = `${role}\n${text}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    cleaned.push({ role, text });
  }
  return cleaned;
}

function normalizeRole(role) {
  const value = String(role || "").toLowerCase();
  if (["assistant", "ai", "model", "bot", "claude"].includes(value)) {
    return "AI";
  }
  if (["user", "human", "you"].includes(value)) {
    return "User";
  }
  if (value.includes("assistant") || value.includes("model") || value.includes("response")) {
    return "AI";
  }
  if (value.includes("user") || value.includes("query")) {
    return "User";
  }
  return null;
}

function cleanText(text) {
  return String(text || "")
    .replace(/\u00a0/g, " ")
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trim())
    .join("\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function isVisible(node) {
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function isMostlyUiText(text) {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return true;
  }
  const uiPhrases = [
    "regenerate",
    "copy",
    "share",
    "thumbs up",
    "thumbs down",
    "double-check response",
    "show drafts",
    "new chat"
  ];
  return uiPhrases.includes(normalized.toLowerCase());
}

function recognitionMessage(messageCount, fileCount) {
  const parts = [`已识别 ${messageCount} 条消息`];
  if (fileCount) {
    parts.push(`${fileCount} 个文本文件`);
  }
  return parts.join("，");
}

function isRuntimeAvailable() {
  try {
    return Boolean(chrome && chrome.runtime && chrome.runtime.id);
  } catch (_error) {
    return false;
  }
}

function isExtensionContextInvalidated(error) {
  return /extension context invalidated/i.test(String((error && error.message) || error || ""));
}

function extensionErrorMessage(error) {
  if (isExtensionContextInvalidated(error)) {
    return "扩展刚刚被重新加载，请刷新当前 AI 页面后再导入。";
  }
  return (error && error.message) || String(error);
}

function titleFromPage(platform, messages) {
  const rawTitle = cleanTitle(document.title || "");
  if (rawTitle && !["chatgpt", "gemini", "claude"].includes(rawTitle.toLowerCase())) {
    return rawTitle;
  }
  const firstUserMessage = messages.find((message) => message.role === "User");
  const firstMessage = firstUserMessage || messages[0];
  if (firstMessage) {
    return firstMessage.text.split("\n")[0].slice(0, 80);
  }
  return `${platform} conversation`;
}

function cleanTitle(title) {
  return String(title || "")
    .replace(/\s*[-|]\s*ChatGPT\s*$/i, "")
    .replace(/\s*[-|]\s*Gemini\s*$/i, "")
    .replace(/\s*[-|]\s*Claude\s*$/i, "")
    .replace(/^Claude\s*-\s*/i, "")
    .trim();
}
