"use strict";

(function initPocketReaderCapture() {
  if (document.querySelector("#pocketreader-capture-root")) {
    return;
  }

  const DEFAULTS = {
    voice: "zh-CN-XiaoxiaoNeural",
    readerMode: "assistant"
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
            <option value="assistant">只读 AI 回复</option>
            <option value="all">朗读全部对话</option>
          </select>
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
  const voiceSelect = root.querySelector("[data-pocketreader-voice]");
  const statusNode = root.querySelector(".pocketreader-status");

  for (const [value, label] of VOICES) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    voiceSelect.append(option);
  }

  chrome.storage.sync.get(DEFAULTS).then((settings) => {
    voiceSelect.value = settings.voice || DEFAULTS.voice;
    readerModeSelect.value = settings.readerMode || DEFAULTS.readerMode;
  });

  openButton.addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) {
      const capture = captureConversation();
      titleInput.value = capture.title;
      showStatus(`已识别 ${capture.messages.length} 条消息`, capture.messages.length ? "" : "error");
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
    const capture = captureConversation();
    capture.title = titleInput.value.trim() || capture.title;
    capture.voice = voiceSelect.value;
    capture.reader_mode = readerModeSelect.value;

    if (!capture.messages.length) {
      showStatus("没有识别到可导入的对话文本。", "error");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "提交中";
    showStatus("正在提交到 PocketReader", "");
    try {
      const response = await chrome.runtime.sendMessage({
        type: "POCKETREADER_CAPTURE_SUBMIT",
        payload: capture
      });
      if (!response || !response.ok) {
        throw new Error(response && response.error ? response.error : "提交失败");
      }
      showStatus(`已创建条目 #${response.result.item_id}`, "ok");
    } catch (error) {
      showStatus(error.message || String(error), "error");
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
      const response = await chrome.runtime.sendMessage({
        type: "POCKETREADER_OPEN_OPTIONS"
      });
      if (!response || !response.ok) {
        throw new Error(response && response.error ? response.error : "无法打开扩展设置。");
      }
    } catch (_error) {
      window.open(chrome.runtime.getURL("options.html"), "_blank");
    }
  }
})();

function captureConversation() {
  const platform = platformFromHost(location.hostname);
  const messages = cleanMessages(extractMessages(platform));
  return {
    platform,
    url: location.href,
    title: titleFromPage(platform, messages),
    messages
  };
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
