# Behavior and safety

## Distraction response

**Settings → Distraction response → Automatically close the verified active
distracting tab (⌘W)** is off by default. Save the setting to apply it.

With auto-close enabled, a distracting classification can send Command-W only
after rechecking the current target and keyboard focus. Command-W closes the
active tab; if it is the last tab, the browser may close its window. This may
lose unsaved page data. Browser save/leave dialogs are not automatically accepted,
and an unverified close is not repeatedly attempted.

After verifying the expected tab closed, the app shows a dismissible desktop
notice naming the tab and explaining its classification. You can request a
correction from the notice. It can remain visible after the active tab changes,
and it hides when the session is paused or ended.

Before dispatch, the app checks:

1. The same session remains active and unpaused, with an unrevoked action lease.
2. Browser bundle/process, window, active tab, URL, title and random document token
   match the classified observation. A reload gets a new document token, even
   with the same URL. Safari's tab index alone is never sufficient for closing.
3. A new full-text snapshot still matches the classified content fingerprint.
4. Native Accessibility reports the browser's matching document window and
   keyboard focus, without a modal dialog/menu/sheet or held modifier keys.
5. A final fresh identity check completes within 750 ms, followed by a fast
   native dispatch veto immediately before PyAutoGUI sends the chord.

Dependencies load before the final validation, never between its authority check
and shortcut dispatch. Page/app changes, pause/end, settings changes and
corrections revoke pending action leases. A model result for an old event may
update its history but cannot authorize closing a newer active page. Missing
identity/permissions, a failed check or an ambiguous state refuses the action
and explains the reason in Status. PyAutoGUI's corner fail-safe remains enabled.

**Important practical limit:** browser state checks and global keyboard dispatch
are separate OS operations. PyAutoGUI cannot atomically lock a specific tab or
keyboard focus. These guards substantially narrow the race and refuse detected
changes, but do not provide a mathematical guarantee against a user switching
focus during the final instant. A fully atomic tab-targeted operation would need
a different browser-native control mechanism. This application is not a
security boundary or tamper-proof blocker.

With auto-close **off**, the same active-page checks precede a reminder. Native
browser full screen is explicitly set to false through Accessibility; HTML/DOM
full screen is exited with `document.exitFullscreen()` when detected and the
page identity is verifiable. The app waits for the transition before displaying
the reminder. It never blindly toggles Control-Command-F.

The reminder is a separate, non-activating topmost Tk panel with **Request
correction…** and **Dismiss**. Its macOS collection behavior lets it join Spaces
(including full-screen auxiliary presentation), so it can appear on the active
desktop without activating the main window or bringing a different desktop
forward. Exact full-screen/multiple-display behavior still needs live validation.
If safe exit/presentation cannot be established, Status reports the refusal.

Three counted distracting observations within ten minutes strengthen the reminder
text. An unchanged page does not count repeatedly. A revisit or changed content
can create another observation. Dismissal hides that warning instance without
changing the classification, count or auto-close setting.

## Correction applications and recovery

Corrections are accessible in the **normal dashboard and reminder**. There is
no hidden developer switch. The dashboard also has **Review last auto-closed
page…**, so a page can be reviewed after it disappears.

A correction requires an active, unpaused session, a different requested label,
a concrete explanation of at least 20 characters, and a five-second confirmation
delay in the application form. The request then goes to the local model.

The review system prompt tells the model to assess evidence rather than obey
instructions in the page or explanation. The user message contains the task,
URL, title, up to 24,000 captured page-text characters, original label and reason,
requested label, and written explanation. Relevant needs a concrete task
connection; uncertain needs evidence of ambiguity or mixed relevance. A wish
to bypass focus controls is insufficient. Only explicit JSON boolean approval
is accepted. Rejection, invalid/truncated output or an unavailable server leaves
the classification unchanged. The model can still make a mistaken judgment;
its approval is not proof of correctness.

Approval is discarded if the session/settings/classification changed during the
review. An accepted correction updates the exact event, repairs its recent
warning count, and saves the correction in the task/page/content/classifier cache.
The explanation and model approval reason are saved on the event. A pending
classifier result cannot replace an approved correction, and a cached correction
wins over another in-flight result for the same key. This does not train the
model or retroactively relabel all historical visits.

If an approved relevant/uncertain correction reverses the latest verified auto
close, the app tries guarded recovery:

- There must be a valid, single-use in-memory close receipt less than 120 seconds
  old. A newer auto-close invalidates the older recovery receipt.
- Browser tab/window metadata must still match the verified post-close state.
  No background page bodies are read for this check.
- The original browser process is activated without a reopen event; the expected
  remaining active tab/window, native keyboard focus and process are rechecked.
- Only then is **Command-Shift-T** sent once. The recovered active URL/title is
  checked. No additional recovery keys are sent if verification fails.

An unverified close, changed browser state, restarted browser, expired receipt,
changed focus or cancelled session refuses recovery. Command-Shift-T is a
browser history command rather than a tab-ID-specific restore: changes to that
history that escape the metadata checks remain a limitation, especially in
Safari. When automatic recovery is refused, use the browser's history manually.

## Uncertain classifications

A valid LLM `uncertain` response automatically triggers another assessment of
that captured page. Attempts send up to **6,000 → 12,000 → 24,000 characters**,
with retry instructions to reconsider the evidence without forcing a definite
answer. A relevant/distracting response stops the sequence early. Only after
three uncertain results does the final uncertain decision remain for review.

Unavailable transport/parser output is an error, not a semantic uncertain
response, and does not trigger three network retries. Uncertain model results
are not cached in a way that suppresses future reassessment. Explicit approved
uncertain corrections retain their intended cached effect. Observation continues
while one inference job runs; only the latest waiting page is retained.

## Reports, storage and privacy

Pause/resume/end, category totals, all-activity/distraction rankings, timeline and
selected-range queries remain available. Sleep or a long monitoring gap pauses
conservatively at the last heartbeat. Interrupted sessions close at that saved
heartbeat on restart; up to about ten seconds before interruption may be omitted.

Default state is `~/Library/Application Support/FocusAssistant/state.json`.
Use `--data-dir ./data` for an isolated store. An exclusive instance lock and
private atomic JSON writes protect saved sessions. Malformed individual records
produce warnings; an unreadable whole file is preserved. Existing development-copy history is not imported automatically.

Tasks, URLs/titles, classification/review reasons, decisions and activity records
are stored locally. Captured page bodies and close receipts stay in memory;
recent review contexts are bounded. Browser topology metadata is used only for
safe close/recovery checks. Requests use loopback addresses, ignore environment
proxies and reject redirects. Do not configure LM Studio to forward requests to
a cloud provider if inference should remain local.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m tests.ui_smoke
node tests/extraction_checks.cjs  # optional development dependency
```

See [CHECKS.md](../CHECKS.md) for recorded results and limits. Close/reopen, native
full-screen and multi-Space behavior are tested through injected interfaces;
they have not been presented as verified live OS interventions.
