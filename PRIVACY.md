# Privacy

- No telemetry, analytics, remote account, cloud API or automatic report upload.
- The active Safari/Chrome page is read during an active focus session. Other
  applications are recorded by name, without their window contents.
- Tasks and captured page text are sent to your configured loopback
  OpenAI-compatible server. This app rejects remote addresses, ignores proxies
  and rejects redirects. A local server may itself log or forward requests;
  configure that server separately if inference must remain entirely local.
- Local state includes settings, tasks, URLs/titles, labels/reasons, approved
  correction explanations, activity times and cached decisions. Extracted page
  bodies and recovery receipts are kept in memory, not stored as a page-body log.
- Close/recovery guards read browser tab/window metadata, including background
  tab URLs/titles. They do not classify background page bodies.
- A random document token is attached to the browser page's window object to
  distinguish reloads/tab changes. It is not an account or cross-site identifier.
- PyAutoGUI sends keyboard chords only. Screen Recording, screenshots, mouse
  tracking and non-browser content inspection are not used.

Default storage is `~/Library/Application Support/FocusAssistant/`. To remove
local history, quit the app and delete that directory yourself. A custom
`--data-dir` has its own state. macOS Automation/Accessibility grants can be
revoked in System Settings → Privacy & Security.

No personal data or previous development session artifacts belong in the source
repository. Diagnostic output is local; review it before voluntarily sharing it.
