# Security and safety reports

For a focus/identity bug, stop the session and disable automatic closing first.
Report enough synthetic reproduction steps to identify which guard failed. Do
not include private page contents, browsing history, credentials or saved state.

Use GitHub's private vulnerability-reporting feature if the repository owner has
enabled it. Otherwise contact the repository owner through an available private
channel before disclosing exploitable details publicly. This project does not
automatically transmit reports or diagnostic data.

Global keyboard shortcuts cannot atomically lock focus. Browser close-history
commands cannot prove that every intervening history change was observed. LLM
approval can be incorrect or influenced by untrusted inputs. This is a personal
focus tool, not parental control, malware protection or a tamper-proof blocker.

Accessibility is powerful access. The app does not grant itself permission,
disable system protections, accept save/leave dialogs, or intentionally inspect
non-browser app content. Unsaved browser data may be lost when auto-close is used.

The current release is experimental. See `CHECKS.md` for verified and unverified
behavior before relying on automatic interventions.
