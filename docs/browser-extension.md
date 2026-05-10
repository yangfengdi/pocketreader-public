# Chrome Extension

The Chrome extension captures conversations from pages where the user is already
logged in, then submits the extracted text to PocketReader.

Supported hosts:

```text
https://chatgpt.com/*
https://chat.openai.com/*
https://gemini.google.com/*
https://claude.ai/*
```

This does not replace ChatGPT share-link import. Share links continue to work
through the normal URL import form. The extension is primarily for Gemini and
Claude, where the server may not be able to fetch the shared page content.

## Install Locally

1. Open Chrome extensions:

```text
chrome://extensions/
```

2. Enable Developer mode.
3. Choose "Load unpacked".
4. Select the repository folder:

```text
browser-extension
```

5. Open the extension options page and set:

```text
PocketReader 地址: https://reader.example.com
IMPORT_TOKEN: value from /etc/apps/pocketreader/pocketreader.env
```

The same values are shown in the logged-in web app at:

```text
https://reader.example.com/extension
```

## Usage

1. Open a ChatGPT, Gemini, or Claude conversation in Chrome.
2. Click the floating "导入 PocketReader" button.
3. Review the title, voice, and reading mode.
4. Click "提交导入".

The extension sends only extracted text, page URL, title, voice, and reading
mode. It does not send AI account cookies to PocketReader.

## Maintenance Notes

Each provider has separate DOM selectors in:

```text
browser-extension/content-script.js
```

If an AI site changes its markup and extraction becomes incomplete, update only
that provider's extractor:

- `extractChatGPTMessages`
- `extractGeminiMessages`
- `extractClaudeMessages`

The backend endpoint is:

```text
POST /api/browser-capture
X-PocketReader-Import-Token: <IMPORT_TOKEN>
```

Payload shape:

```json
{
  "platform": "gemini",
  "url": "https://gemini.google.com/...",
  "title": "Conversation title",
  "reader_mode": "assistant",
  "voice": "zh-CN-XiaoxiaoNeural",
  "messages": [
    {"role": "User", "text": "Question"},
    {"role": "AI", "text": "Answer"}
  ]
}
```
