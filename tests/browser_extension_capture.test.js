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
