"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "browser-extension", "content-script.js"),
  "utf8"
);

const context = {
  console,
  document: {
    querySelector(selector) {
      return selector === "#pocketreader-capture-root" ? {} : null;
    }
  },
  window: {
    getComputedStyle() {
      return { visibility: "visible", display: "block" };
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context);

function test(name, fn) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("splitMessagesIntoTurns keeps three Claude question-answer turns", () => {
  const turns = context.splitMessagesIntoTurns([
    { role: "User", text: "问题一" },
    { role: "AI", text: "回答一" },
    { role: "User", text: "问题二" },
    { role: "AI", text: "回答二" },
    { role: "User", text: "问题三" },
    { role: "AI", text: "回答三" }
  ]);

  assert.strictEqual(turns.length, 3);
  assert.strictEqual(
    JSON.stringify(turns.map((turn) => turn.map((message) => message.role))),
    JSON.stringify([
      ["User", "AI"],
      ["User", "AI"],
      ["User", "AI"]
    ])
  );
});

test("hasBothConversationRoles rejects assistant-only Claude captures", () => {
  assert.strictEqual(
    context.hasBothConversationRoles([
      { role: "AI", text: "回答一" },
      { role: "AI", text: "回答二" },
      { role: "AI", text: "回答三" }
    ]),
    false
  );
});

test("cleanMessages replaces partial duplicate assistant fragments with full text", () => {
  const fullText =
    "这是一段较长的 Claude 回复，包含完整内容和第二句话。它模拟同一个回复节点和内部段落节点被同时抓到的情况，需要只保留完整回复。";
  const fragment = "完整内容和第二句话。它模拟同一个回复节点和内部段落节点被同时抓到的情况";
  const messages = context.cleanMessages([
    { role: "AI", text: fullText },
    { role: "AI", text: fragment }
  ]);

  assert.strictEqual(messages.length, 1);
  assert.strictEqual(messages[0].text, fullText);
});

test("recognitionMessage warns when only one side was captured", () => {
  const message = context.recognitionMessage(
    [
      { role: "AI", text: "回答一" },
      { role: "AI", text: "回答二" }
    ],
    0
  );

  assert.ok(message.includes("未完整识别问答双方"));
});

test("streaming guards identify active generation signals", () => {
  assert.strictEqual(context.isActiveStreamingValue("true"), true);
  assert.strictEqual(context.isActiveStreamingValue("1"), true);
  assert.strictEqual(context.isActiveStreamingValue("false"), false);
  assert.strictEqual(context.isActiveStreamingValue("0"), false);
  assert.strictEqual(context.isStopGenerationLabel("Stop generating"), true);
  assert.strictEqual(context.isStopGenerationLabel("停止生成"), true);
  assert.strictEqual(context.isStopGenerationLabel("Copy response"), false);
});

test("Claude collapsed user previews are not treated as assistant fallback", () => {
  const preview = fakeNode({
    className: "flex-1 min-w-0 overflow-hidden text-[8px] text-text-500/80 break-all line-clamp-[6]",
    text: "关于辩证法，听你刚才讲完，我开始形成了一些直觉，想请你帮我整理成一篇文章，并对我的这些看法做出评价。",
    width: 99,
    height: 72
  });

  assert.strictEqual(context.isClaudeCollapsedUserPreviewNode(preview), true);
  assert.strictEqual(context.isClaudeAssistantFallbackNode(preview), false);
});

test("Claude standalone bold headings are treated as assistant fallback text", () => {
  const assistantContext = {
    closest(selector) {
      return selector === "main" ? {} : null;
    }
  };
  const heading = fakeNode({
    tagName: "strong",
    text: "艺术与品味",
    closestBySelector(selector) {
      if (selector.includes("font-claude-message")) {
        return assistantContext;
      }
      return null;
    }
  });

  assert.strictEqual(context.isClaudeAssistantStandaloneFormattingNode(heading), true);
  assert.strictEqual(context.isClaudeAssistantFallbackNode(heading), true);
});

test("Claude inline bold spans are not duplicated as standalone fallback text", () => {
  const assistantContext = {
    closest(selector) {
      return selector === "main" ? {} : null;
    }
  };
  const inline = fakeNode({
    tagName: "strong",
    text: "艺术与品味",
    textSiblings: ["这里讨论", "这个概念。"],
    closestBySelector(selector) {
      if (selector.split(",").map((part) => part.trim()).includes("p")) {
        return {};
      }
      if (selector.includes("font-claude-message")) {
        return assistantContext;
      }
      return null;
    }
  });

  assert.strictEqual(context.isClaudeAssistantStandaloneFormattingNode(inline), false);
});

function fakeNode({
  className = "",
  tagName = "div",
  text = "",
  width = 100,
  height = 40,
  closestResult = null,
  closestBySelector = null,
  textSiblings = []
}) {
  const node = {
    tagName,
    innerText: text,
    textContent: text,
    parentElement: null,
    childNodes: [],
    getAttribute(name) {
      return name === "class" ? className : "";
    },
    getBoundingClientRect() {
      return { width, height };
    },
    closest(selector) {
      if (closestBySelector) {
        return closestBySelector(selector);
      }
      return closestResult;
    },
    querySelector() {
      return null;
    }
  };
  node.parentElement = {
    innerText: [textSiblings[0] || "", text, textSiblings[1] || ""].join(""),
    textContent: [textSiblings[0] || "", text, textSiblings[1] || ""].join(""),
    childNodes: [
      { nodeType: 3, textContent: textSiblings[0] || "" },
      node,
      { nodeType: 3, textContent: textSiblings[1] || "" }
    ]
  };
  return {
    ...node
  };
}
