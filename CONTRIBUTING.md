# Contributing

Use synthetic fixtures for tests. Do not commit a real ledger, log, game binary, calibration image, profile, PIN, cookie or token. The public-tree check is required before a release.

Keep the recorder and game lifecycle separate from changing a target: Next and Skip must never start, stop or close the game. Preserve original timestamps and mark uncertain events honestly.

The main Windows workflow is the reproducible build and test entry point. Include a focused regression check when changing state, uploads, menus or capture boundaries. Use normal menu controls only; anti-cheat bypasses and kernel drivers are outside this project.

For a bug report, include the release version, Windows version, a redacted error and whether a synthetic reproduction is available. Follow SECURITY.md for sensitive reports.
