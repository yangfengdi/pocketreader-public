# Requirements

## User Need

The user often consumes information by listening. The app should turn text,
Markdown, AI conversations, and batches of files into audio that can be played on
an iPhone, including while driving or reviewing drafts by ear.

## Primary Workflows

1. Desktop import, phone listening:
   - Open the web app on a computer.
   - Paste text or upload multiple Markdown/text files.
   - Wait for TTS generation.
   - Open the same app on iPhone and listen through the queue.

2. Phone link import:
   - Copy or share a public AI conversation link.
   - Paste it into PocketReader.
   - Select whether to read only AI replies or the full conversation.

3. Desktop browser capture:
   - Open ChatGPT, Gemini, or Claude in Chrome.
   - Click the injected "导入 PocketReader" button in the AI page.
   - Select title, voice, and whether to read only AI replies or the full
     conversation.
   - Submit the visible conversation text to PocketReader without creating a
     public share link.

4. Draft review:
   - Paste or upload a draft.
   - Generate audio.
   - Listen, pause, resume, and review progress later.

5. Offline preparation:
   - Open an item page on iPhone.
   - Tap the cache button to store that MP3 in the browser cache.
   - Optionally subscribe to the private podcast feed in a podcast app that can
     download episodes.

## Functional Requirements

- Single-owner login.
- Import text and Markdown.
- Batch upload `.txt`, `.md`, and `.markdown`.
- Import public URLs.
- Best-effort parsing for ChatGPT, Gemini, and Claude share pages.
- Chrome extension import for logged-in ChatGPT, Gemini, and Claude pages.
- Default conversation mode: AI replies only.
- Optional conversation mode: user and AI.
- Voice choice in the UI.
- Queue TTS jobs.
- Split long text so each TTS request is under the provider limit.
- Merge chunks into a single MP3 per item.
- Persist item status and history.
- Resume playback from the last position.
- Mark completed items.
- Auto-open the next ready item after playback ends.
- Private podcast RSS feed.

## Non-Goals For Version 1

- Native iOS app.
- Multi-user accounts.
- Remote-server login automation for private AI pages.
- Automatic audio deletion policy.
- Full-text search.
