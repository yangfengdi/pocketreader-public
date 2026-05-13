"use strict";

var POCKETREADER_MAX_FILE_TEXT_CHARS = 300000;
var POCKETREADER_MAX_BINARY_FILE_BYTES = 4 * 1024 * 1024;
var POCKETREADER_TEXT_FILE_EXTENSIONS = new Set([
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
var POCKETREADER_BINARY_DOCUMENT_EXTENSIONS = new Set(["docx"]);
var POCKETREADER_FORCED_ROLE_HINTS = new WeakMap();

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
  let latestSnapshotResult = null;

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

  openButton.addEventListener("click", async () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) {
      await parseCurrentPage();
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
    if (!latestSnapshotResult || !latestSnapshotResult.capture_id) {
      await parseCurrentPage();
    }
    if (!latestSnapshotResult || !latestSnapshotResult.capture_id) {
      showStatus("没有识别到可导入的对话文本或文本文件。", "error");
      return;
    }
    if (!snapshotResultHasContent(latestSnapshotResult)) {
      showStatus("没有识别到可导入的对话文本或文本文件。", "error");
      return;
    }
    const summary = latestSnapshotResult.summary || {};
    if (splitTurnsInput.checked && readerModeSelect.value !== "assistant" && !summary.has_user_messages) {
      showStatus("没有完整识别到问题和 AI 回复，已停止提交。请刷新页面后重试。", "error");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "提交中";
    showStatus("正在提交到 PocketReader", "");
    try {
      const response = await sendRuntimeMessage({
        type: "POCKETREADER_SNAPSHOT_CREATE",
        payload: {
          capture_id: latestSnapshotResult.capture_id,
          title: titleInput.value.trim() || latestSnapshotResult.title,
          voice: voiceSelect.value,
          reader_mode: readerModeSelect.value,
          split_by_turn: splitTurnsInput.checked,
          include_user_question: readerModeSelect.value !== "assistant"
        }
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

  async function parseCurrentPage() {
    showStatus("正在把页面快照提交给服务器解析", "");
    try {
      const snapshot = await capturePageSnapshot();
      const response = await sendRuntimeMessage({
        type: "POCKETREADER_SNAPSHOT_PARSE",
        payload: snapshot
      });
      if (!response || !response.ok) {
        throw new Error(response && response.error ? response.error : "解析失败");
      }
      latestSnapshotResult = response.result || null;
      if (latestSnapshotResult && latestSnapshotResult.title) {
        titleInput.value = latestSnapshotResult.title;
      } else {
        titleInput.value = snapshot.title;
      }
      const state = snapshotResultHasContent(latestSnapshotResult) ? "" : "error";
      showStatus(snapshotRecognitionMessage(latestSnapshotResult), state);
    } catch (error) {
      latestSnapshotResult = null;
      showStatus(extensionErrorMessage(error), "error");
    }
  }

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

async function capturePageSnapshot() {
  const platform = platformFromHost(location.hostname);
  const blocks = collectSnapshotBlocks(platform);
  const files = await extractGeneratedFiles(platform, messagesFromSnapshotBlocks(blocks));
  const title = cleanTitle(document.title || "") || titleFromSnapshotBlocks(platform, blocks);
  return {
    platform,
    url: location.href,
    title,
    extension_version: extensionVersion(),
    snapshot: {
      page: {
        platform,
        url: location.href,
        host: location.hostname,
        title: cleanTitle(document.title || "")
      },
      blocks,
      files
    }
  };
}

function messagesFromSnapshotBlocks(blocks) {
  return blocks
    .filter((block) => block.kind_hint === "message" && normalizeRole(block.role_hint))
    .map((block) => ({
      role: normalizeRole(block.role_hint),
      text: block.text
    }));
}

function collectSnapshotBlocks(platform) {
  const nodes = [];
  const seen = new Set();
  for (const selector of snapshotSelectors(platform)) {
    for (const node of document.querySelectorAll(selector)) {
      if (!isVisible(node) || seen.has(node)) {
        continue;
      }
      seen.add(node);
      nodes.push(node);
    }
  }
  if (platform === "claude") {
    addClaudeFallbackTextNodes(nodes, seen);
  }

  return nodes
    .sort(compareDomNodeOrder)
    .map((node, index) => snapshotBlockFromNode(node, platform, index))
    .filter((block) => block.text.length >= 2);
}

function snapshotSelectors(platform) {
  const commonFileSelectors = [
    "main a[download]",
    "main a[href]",
    "main [data-testid*='file' i]",
    "main [data-testid*='attachment' i]",
    "main [aria-label*='download' i]",
    "main [title*='download' i]"
  ];
  if (platform === "chatgpt") {
    return [
      "[data-message-author-role]",
      "[data-testid*='user-message']",
      "[data-testid*='assistant-message']",
      ...commonFileSelectors
    ];
  }
  if (platform === "gemini") {
    return [
      "user-query",
      "[data-test-id='user-query']",
      "[data-testid='user-query']",
      ".query-text",
      "model-response",
      "[data-test-id='model-response']",
      "[data-testid='model-response']",
      ".model-response-text",
      ".response-container",
      "message-content",
      ...commonFileSelectors
    ];
  }
  if (platform === "claude") {
    return [
      "[data-testid='user-message']",
      "[data-testid*='user-message']",
      "[data-testid='assistant-message']",
      "[data-testid*='assistant-message']",
      ".font-user-message",
      ".font-claude-message",
      "[data-testid*='artifact' i]",
      "[aria-label*='artifact' i]",
      "[title*='artifact' i]",
      "[class*='artifact' i]",
      "[data-testid*='canvas' i]",
      "[class*='canvas' i]",
      ...commonFileSelectors
    ];
  }
  return ["article", "main", ...commonFileSelectors];
}

function addClaudeFallbackTextNodes(nodes, seen) {
  const root = document.querySelector("main") || document.body;
  if (!root) {
    return;
  }
  const selectors = [
    "p",
    "li",
    "blockquote",
    "pre",
    "code",
    "h1",
    "h2",
    "h3",
    "h4",
    "[class*='prose' i]",
    "[class*='markdown' i]",
    "[class*='leading-' i]",
    "[class*='whitespace-pre-wrap' i]"
  ].join(",");
  for (const node of root.querySelectorAll(selectors)) {
    if (seen.has(node) || !isClaudeAssistantFallbackNode(node)) {
      continue;
    }
    POCKETREADER_FORCED_ROLE_HINTS.set(node, "AI");
    seen.add(node);
    nodes.push(node);
  }
}

function isClaudeAssistantFallbackNode(node) {
  if (!isVisible(node)) {
    return false;
  }
  const className = String(node.getAttribute("class") || "").toLowerCase();
  if (className.includes("sr-only") || className.includes("screen-reader")) {
    return false;
  }
  if (openDocumentRoot(node)) {
    return false;
  }
  if (
    node.closest(
      [
        "#pocketreader-capture-root",
        "nav",
        "aside",
        "header",
        "footer",
        "form",
        "textarea",
        "[contenteditable='true']",
        "[data-testid*='user-message' i]",
        ".font-user-message",
        "[aria-label='New chat']",
        "[aria-label='Search']",
        "[aria-label='Chats']"
      ].join(",")
    )
  ) {
    return false;
  }
  if (node.querySelector("[data-testid*='user-message' i], .font-user-message")) {
    return false;
  }
  const text = cleanText(node.innerText || node.textContent || "");
  if (text.length < 20 || isMostlyUiText(text) || text.includes("Claude is AI and can make mistakes")) {
    return false;
  }
  return true;
}

function snapshotBlockFromNode(node, platform, index) {
  const kindHint = kindHintFromNode(node);
  const text =
    kindHint === "artifact"
      ? artifactBodyFromNode(node) || textFromNode(readableChild(node) || node)
      : textFromNode(readableChild(node) || node);
  return {
    index,
    tag: node.tagName ? node.tagName.toLowerCase() : "",
    path: elementPath(node),
    role_hint: POCKETREADER_FORCED_ROLE_HINTS.get(node) || roleHintFromNode(node, platform),
    kind_hint: kindHint,
    attrs: snapshotAttrs(node),
    rect: snapshotRect(node),
    text: cleanText(text).slice(0, POCKETREADER_MAX_FILE_TEXT_CHARS)
  };
}

function roleHintFromNode(node, platform) {
  const explicitRole = normalizeRole(node.getAttribute("data-message-author-role"));
  if (explicitRole) {
    return explicitRole;
  }
  const haystack = [
    platform,
    node.tagName || "",
    node.getAttribute("data-testid") || "",
    node.getAttribute("data-test-id") || "",
    node.getAttribute("class") || "",
    node.getAttribute("aria-label") || ""
  ]
    .join(" ")
    .toLowerCase();
  if (
    haystack.includes("assistant-message") ||
    haystack.includes("model-response") ||
    haystack.includes("font-claude-message") ||
    haystack.includes("message-content") ||
    haystack.includes("response-container")
  ) {
    return "AI";
  }
  if (
    haystack.includes("user-message") ||
    haystack.includes("user-query") ||
    haystack.includes("font-user-message") ||
    haystack.includes("query-text")
  ) {
    return "User";
  }
  return "";
}

function kindHintFromNode(node) {
  const haystack = [
    node.getAttribute("data-testid") || "",
    node.getAttribute("class") || "",
    node.getAttribute("aria-label") || "",
    node.getAttribute("title") || ""
  ]
    .join(" ")
    .toLowerCase();
  if (haystack.includes("artifact") || haystack.includes("canvas")) {
    return "artifact";
  }
  if (fileNameFromNode(node) || /file|download|attachment/.test(haystack)) {
    return "file";
  }
  return "message";
}

function snapshotAttrs(node) {
  const attrs = {};
  for (const name of [
    "data-message-author-role",
    "data-testid",
    "data-test-id",
    "class",
    "aria-label",
    "title",
    "role",
    "download",
    "href"
  ]) {
    const value = name === "href" ? hrefFromNode(node) : node.getAttribute(name);
    if (value) {
      attrs[name] = String(value).slice(0, 500);
    }
  }
  return attrs;
}

function snapshotRect(node) {
  const rect = node.getBoundingClientRect();
  return {
    top: Math.round(rect.top),
    left: Math.round(rect.left),
    width: Math.round(rect.width),
    height: Math.round(rect.height)
  };
}

function elementPath(node) {
  const parts = [];
  let current = node;
  while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
    let part = current.tagName.toLowerCase();
    const testId = current.getAttribute("data-testid");
    if (testId) {
      part += `[data-testid="${testId.slice(0, 80)}"]`;
    } else if (current.id) {
      part += `#${current.id.slice(0, 80)}`;
    }
    parts.unshift(part);
    current = current.parentElement;
  }
  return parts.join(" > ");
}

function titleFromSnapshotBlocks(platform, blocks) {
  const firstUser = blocks.find((block) => block.role_hint === "User");
  const firstMessage = firstUser || blocks.find((block) => block.role_hint === "AI");
  if (firstMessage && firstMessage.text) {
    return firstMessage.text.split("\n")[0].slice(0, 80);
  }
  return `${platform} conversation`;
}

function extensionVersion() {
  try {
    if (isRuntimeAvailable() && typeof chrome.runtime.getManifest === "function") {
      return chrome.runtime.getManifest().version || "";
    }
  } catch (_error) {
    return "";
  }
  return "";
}

function captureConversation() {
  const platform = platformFromHost(location.hostname);
  const messages = cleanMessages(extractMessages(platform));
  return {
    platform,
    url: location.href,
    title: titleFromPage(platform, messages),
    messages,
    files: [],
    file_count: 0
  };
}

async function captureConversationWithFiles() {
  const capture = captureConversation();
  capture.files = await extractGeneratedFiles(capture.platform, capture.messages);
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
  const structuredMessages = collectCandidates([
    ["User", "[data-testid='user-message'], [data-testid*='user-message']"],
    ["AI", "[data-testid='assistant-message'], [data-testid*='assistant-message']"]
  ]);
  if (hasBothConversationRoles(structuredMessages)) {
    return structuredMessages;
  }

  return collectCandidates([
    ["User", ".font-user-message"],
    ["AI", ".font-claude-message"]
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

function hasBothConversationRoles(messages) {
  return (
    messages.some((message) => normalizeRole(message.role) === "User") &&
    messages.some((message) => normalizeRole(message.role) === "AI")
  );
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
  return compareDomNodeOrder(a.node, b.node);
}

function compareDomNodeOrder(a, b) {
  if (a === b) {
    return 0;
  }
  return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_PRECEDING ? 1 : -1;
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

async function extractGeneratedFiles(platform, messages = []) {
  const candidates = collectGeneratedFileCandidates(platform, messages);
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

function collectGeneratedFileCandidates(platform, messages = []) {
  const candidates = [];
  const scopes = fileSearchScopes(platform);
  for (const scope of scopes) {
    for (const node of scope.querySelectorAll("a[download], a[href], [data-testid], [aria-label], [title]")) {
      addFileCandidate(candidates, node);
    }
  }
  if (platform === "claude") {
    addClaudeArtifactCandidates(candidates, messages);
    addClaudeOpenDocumentCandidates(candidates, messages);
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
  if (candidate.inline_body) {
    return {
      title: candidate.title,
      filename: candidate.filename,
      body: candidate.inline_body,
      url: candidate.url || null
    };
  }
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

function addClaudeArtifactCandidates(candidates, messages = []) {
  const nodes = Array.from(
    document.querySelectorAll(
      [
        "[data-testid*='artifact' i]",
        "[aria-label*='artifact' i]",
        "[title*='artifact' i]",
        "[class*='artifact' i]",
        "[data-testid*='canvas' i]",
        "[class*='canvas' i]"
      ].join(",")
    )
  )
    .filter(isVisible)
    .sort(compareNodeDepth);

  for (const node of nodes) {
    const body = artifactBodyFromNode(node);
    if (!body || overlapsKnownMessages(body, messages)) {
      continue;
    }
    const title = artifactTitleFromNode(node, body);
    const filename = `${safeFilename(title || "claude-artifact")}.md`;
    const key = `claude-artifact\n${title}\n${body.slice(0, 500)}`;
    addInlineFileCandidate(candidates, {
      key,
      node,
      title: title || filename,
      filename,
      url: "",
      inline_body: body
    });
  }
}

function addClaudeOpenDocumentCandidates(candidates, messages = []) {
  const contentNodes = Array.from(
    document.querySelectorAll(
      [
        ".cm-content",
        ".ProseMirror",
        "[contenteditable='true']",
        "textarea",
        "pre",
        "code",
        "article",
        ".standard-markdown",
        ".progressive-markdown",
        "[class*='markdown' i]"
      ].join(",")
    )
  )
    .filter(isVisible)
    .sort(compareNodeDepth);

  for (const contentNode of contentNodes) {
    const root = openDocumentRoot(contentNode);
    if (!root || !isVisible(root)) {
      continue;
    }
    const body = artifactBodyFromNode(root);
    if (!body || overlapsKnownMessages(body, messages)) {
      continue;
    }
    const title = artifactTitleFromNode(root, body);
    const key = `claude-open-document\n${title}\n${body.slice(0, 500)}`;
    addInlineFileCandidate(candidates, {
      key,
      node: root,
      title: title || "Claude Markdown",
      filename: `${safeFilename(title || "claude-markdown")}.md`,
      url: "",
      inline_body: body
    });
  }
}

function openDocumentRoot(node) {
  if (node.closest("[data-testid*='user-message' i], .font-user-message")) {
    return null;
  }
  const root =
    node.closest(
      [
        "[data-testid*='artifact' i]",
        "[class*='artifact' i]",
        "[data-testid*='canvas' i]",
        "[class*='canvas' i]",
        "[class*='document' i]",
        "[class*='preview' i]",
        "[class*='editor' i]",
        "[class*='panel' i]",
        "[class*='modal' i]",
        "[class*='drawer' i]",
        "[data-testid*='panel' i]",
        "[data-testid*='modal' i]",
        "[data-testid*='drawer' i]",
        "[role='dialog']",
        "aside"
      ].join(",")
    ) || node;
  if (isPlainConversationMarkdown(node, root)) {
    return null;
  }
  if (!hasOpenDocumentSignal(root, node)) {
    return null;
  }
  return root;
}

function isPlainConversationMarkdown(node, root) {
  const conversationNode = node.closest(
    [
      "[data-testid*='assistant-message' i]",
      ".font-claude-message",
      ".font-claude-response",
      ".standard-markdown",
      ".progressive-markdown"
    ].join(",")
  );
  if (!conversationNode) {
    return false;
  }
  if (root && root !== node && explicitDocumentRootSignal(root)) {
    return false;
  }
  return Boolean(conversationNode.closest("main"));
}

function explicitDocumentRootSignal(root) {
  const attributes = [
    root.getAttribute("data-testid"),
    root.getAttribute("class"),
    root.getAttribute("aria-label"),
    root.getAttribute("title"),
    root.getAttribute("role")
  ]
    .join(" ")
    .toLowerCase();
  return /artifact|canvas|document|preview|editor|panel|modal|drawer|dialog/.test(attributes);
}

function hasOpenDocumentSignal(root, contentNode) {
  const attributes = [
    root.getAttribute("data-testid"),
    root.getAttribute("class"),
    root.getAttribute("aria-label"),
    root.getAttribute("title"),
    contentNode.getAttribute("class"),
    contentNode.getAttribute("aria-label"),
    contentNode.getAttribute("title")
  ]
    .join(" ")
    .toLowerCase();
  if (/artifact|canvas|document|preview|editor|panel|modal|drawer|markdown|code|file/.test(attributes)) {
    return true;
  }
  if (
    root.querySelector(
      ".cm-content, .ProseMirror, [contenteditable='true'], textarea, [role='tablist'], [data-testid*='toolbar' i], [class*='toolbar' i]"
    )
  ) {
    return true;
  }
  const toolbarText = cleanText(
    Array.from(root.querySelectorAll("button, [role='button'], [aria-label], [title]"))
      .map((node) => node.getAttribute("aria-label") || node.getAttribute("title") || node.textContent || "")
      .join("\n")
  );
  return /(copy|download|preview|code|markdown|复制|下载|预览|代码)/i.test(toolbarText);
}

function addInlineFileCandidate(candidates, candidate) {
  if (!candidate.inline_body) {
    return;
  }
  if (candidates.some((existing) => existing.key === candidate.key)) {
    return;
  }
  const overlapIndex = candidates.findIndex(
    (existing) => existing.inline_body && textContainsEither(existing.inline_body, candidate.inline_body)
  );
  if (overlapIndex >= 0) {
    if (candidate.inline_body.length > candidates[overlapIndex].inline_body.length) {
      candidates[overlapIndex] = candidate;
    }
    return;
  }
  candidates.push(candidate);
}

function artifactBodyFromNode(node) {
  const preferred = artifactContentNode(node);
  const rawText = preferred ? textFromArtifactNode(preferred) : textFromArtifactNode(node);
  const text = stripArtifactUiLines(rawText);
  if (!looksLikeArtifactBody(text)) {
    return "";
  }
  return text.slice(0, POCKETREADER_MAX_FILE_TEXT_CHARS);
}

function artifactContentNode(node) {
  return (
    node.querySelector("[data-testid*='artifact-content' i]") ||
    node.querySelector("[data-testid*='artifact_content' i]") ||
    node.querySelector("[class*='artifact-content' i]") ||
    node.querySelector("[class*='artifact_content' i]") ||
    node.querySelector(".cm-content") ||
    node.querySelector(".ProseMirror") ||
    node.querySelector("[contenteditable='true']") ||
    node.querySelector("article") ||
    node.querySelector("main") ||
    node.querySelector("pre") ||
    node.querySelector("code") ||
    node.querySelector("textarea") ||
    null
  );
}

function textFromArtifactNode(node) {
  const iframeText = textFromSameOriginIframes(node);
  if (iframeText) {
    return iframeText;
  }
  const clone = node.cloneNode(true);
  for (const removable of clone.querySelectorAll(
    [
      "button",
      "svg",
      "style",
      "script",
      "textarea",
      "input",
      "select",
      "nav",
      "menu",
      "[aria-hidden='true']",
      "[hidden]",
      "[role='toolbar']",
      "[role='tablist']",
      "[data-testid*='toolbar' i]",
      "[class*='toolbar' i]"
    ].join(",")
  )) {
    removable.remove();
  }
  return cleanText(clone.innerText || clone.textContent || "");
}

function textFromSameOriginIframes(node) {
  const parts = [];
  for (const iframe of node.querySelectorAll("iframe")) {
    try {
      const body = iframe.contentDocument && iframe.contentDocument.body;
      if (body) {
        const text = textFromNode(body);
        if (text) {
          parts.push(text);
        }
      }
    } catch (_error) {
      continue;
    }
  }
  return cleanText(parts.join("\n\n"));
}

function stripArtifactUiLines(text) {
  const uiLinePattern =
    /^(artifact|preview|code|copy|download|publish|close|open|复制|下载|预览|代码|发布|关闭|打开|复制内容|复制代码)$/i;
  return cleanText(
    String(text || "")
      .split("\n")
      .filter((line) => !uiLinePattern.test(line.trim()))
      .join("\n")
  );
}

function looksLikeArtifactBody(text) {
  const value = cleanText(text);
  if (value.length < 40) {
    return false;
  }
  const lines = value.split("\n").filter(Boolean);
  return lines.length >= 2 || /[。.!?？]\s/.test(value) || value.length >= 120;
}

function artifactTitleFromNode(node, body) {
  const candidates = [
    textFromFirst(node, "h1, h2, h3"),
    textFromFirst(node, "[data-testid*='title' i]"),
    node.getAttribute("title"),
    node.getAttribute("aria-label"),
    body.split("\n").find((line) => line.trim().length >= 2 && line.trim().length <= 90),
    cleanTitle(document.title || "")
  ];
  for (const candidate of candidates) {
    const title = cleanArtifactTitle(candidate);
    if (title) {
      return title;
    }
  }
  return "Claude Artifact";
}

function textFromFirst(node, selector) {
  const found = node.querySelector(selector);
  return found ? cleanText(found.textContent || "") : "";
}

function cleanArtifactTitle(title) {
  const value = cleanText(title)
    .replace(/\b(artifact|preview|code)\b/gi, "")
    .replace(/^(复制|下载|预览|代码)\s*/g, "")
    .trim();
  if (!value || value.length > 120 || /^(artifact|preview|code)$/i.test(value)) {
    return "";
  }
  return value;
}

function safeFilename(name) {
  const cleaned = String(name || "")
    .replace(/[\\/:*?"<>|]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 90);
  return cleaned || "claude-artifact";
}

function compareNodeDepth(a, b) {
  return nodeDepth(b) - nodeDepth(a);
}

function nodeDepth(node) {
  let depth = 0;
  let current = node;
  while (current && current.parentElement) {
    depth += 1;
    current = current.parentElement;
  }
  return depth;
}

function sameBody(a, b) {
  const left = cleanText(a).slice(0, 1000);
  const right = cleanText(b).slice(0, 1000);
  return left === right || left.includes(right) || right.includes(left);
}

function textContainsEither(left, right) {
  const normalizedLeft = canonicalComparableText(left);
  const normalizedRight = canonicalComparableText(right);
  if (!normalizedLeft || !normalizedRight) {
    return false;
  }
  if (normalizedLeft === normalizedRight) {
    return true;
  }
  const shorter = normalizedLeft.length < normalizedRight.length ? normalizedLeft : normalizedRight;
  const longer = normalizedLeft.length < normalizedRight.length ? normalizedRight : normalizedLeft;
  if (shorter.length < 20) {
    return false;
  }
  return longer.includes(shorter);
}

function canonicalComparableText(text) {
  return cleanText(text).replace(/\s+/g, " ").trim();
}

function overlapsKnownMessages(body, messages = []) {
  const candidate = cleanText(body);
  if (!candidate) {
    return false;
  }
  for (const message of messages) {
    const text = cleanText(message.text || "");
    if (!text || text.length < 40) {
      continue;
    }
    if (sameBody(candidate, text)) {
      return true;
    }
  }
  return false;
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
  for (const message of messages) {
    const role = normalizeRole(message.role);
    const text = cleanText(message.text).replace(/^(ChatGPT|Gemini|Claude|You|User|Assistant)\s*\n/i, "");
    if (!role || text.length < 2 || isMostlyUiText(text)) {
      continue;
    }

    const duplicateIndex = cleaned.findIndex(
      (existing) => existing.role === role && textContainsEither(existing.text, text)
    );
    if (duplicateIndex >= 0) {
      if (text.length > cleaned[duplicateIndex].text.length) {
        cleaned[duplicateIndex] = { role, text };
      }
      continue;
    }

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

function recognitionMessage(messages, fileCount) {
  const turns = splitMessagesIntoTurns(messages);
  const userCount = messages.filter((message) => normalizeRole(message.role) === "User").length;
  const aiCount = messages.filter((message) => normalizeRole(message.role) === "AI").length;
  const parts = [`已识别 ${messages.length} 条消息`];
  if (turns.length) {
    parts.push(`${turns.length} 个回合`);
  }
  if (messages.length && (!userCount || !aiCount)) {
    parts.push("未完整识别问答双方");
  }
  if (fileCount) {
    parts.push(`${fileCount} 个文本文件`);
  }
  return parts.join("，");
}

function snapshotRecognitionMessage(result) {
  if (!result) {
    return "服务器没有返回解析结果";
  }
  const summary = result.summary || {};
  const messageCount = Number(summary.message_count || 0);
  const turnCount = Number(summary.turn_count || 0);
  const fileCount = Number(summary.file_count || 0);
  const parts = [`服务器已识别 ${messageCount} 条消息`];
  if (turnCount) {
    parts.push(`${turnCount} 个回合`);
  }
  if (fileCount) {
    parts.push(`${fileCount} 个文本文件`);
  }
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  if (warnings.length) {
    parts.push(warnings.join("，"));
  }
  return parts.join("，");
}

function snapshotResultHasContent(result) {
  const summary = (result && result.summary) || {};
  return Boolean(Number(summary.message_count || 0) || Number(summary.file_count || 0));
}

function splitMessagesIntoTurns(messages) {
  const turns = [];
  let currentTurn = [];
  let hasAiMessage = false;

  for (const message of messages) {
    const role = normalizeRole(message.role);
    if (!role || !cleanText(message.text || "")) {
      continue;
    }
    if (role === "User") {
      if (hasAiMessage) {
        turns.push(currentTurn);
        currentTurn = [];
        hasAiMessage = false;
      }
      currentTurn.push(message);
      continue;
    }
    currentTurn.push(message);
    hasAiMessage = true;
  }

  if (currentTurn.length && hasAiMessage) {
    turns.push(currentTurn);
  }
  return turns;
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
