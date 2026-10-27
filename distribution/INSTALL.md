# Hardware Design Skill 1.0.1

Requires Python 3.10+ and an AI client with local file/command access.
Extract the entire installer ZIP before running it. On Windows, double-click
Manage-Skill.cmd. Choose one client. The installer does not install the client,
EasyEDA, easyeda-agent or its Connector.

Command-line installation (from this extracted folder):

    python skill_update.py install --client claude --package design-hardware-1.0.1.zip --manifest release.json
    python skill_update.py status --client claude
    python skill_update.py rollback --client claude

Use --client codex or --client workbuddy as appropriate. A pre-existing manual
installation requires explicit --adopt. Local edits are protected. Reload the
skill in your client after changing installed files. A healthy file inventory
does not prove client loading or EDA connectivity.

Verify the outer installer against the separately downloaded SHA256SUMS from
the same trusted release. release.json binds the inner archive and its files.
Hashes detect corruption; they are not publisher signatures.

Feedback-loop writes and full automatic strict compose acceptance remain
experimental. Offline checks do not certify manufacturing or hardware function.
Read the complete scope and limitations at:
https://github.com/zsx3896926/hardware-design-skill/blob/v1.0.1/docs/releases/v1.0.1.md

This is an independently maintained project, not an official JLC product.
Apache License 2.0: see LICENSE. External tools have their own licenses.
