# Review and validation scope

The private prototype was reviewed across the native recorder bridge, launcher, capture/export lifecycle, journal persistence, dashboard, mission selection, optional menu return, overlay, upload queue, browser connector and packaging.

## Changes made for publication

| Finding | Change |
| --- | --- |
| Absolute machine paths, a fixed character, local screenshots and saved state could not be shared | Source-only staging; per-user data directory; Steam discovery; user-calibrated images stored outside the repository |
| Bootstrap downloads were not hash checked and required Portable Git | Fixed Python, pip-wheel and engine URLs with SHA-256 checks; direct extraction from a pinned engine archive |
| First-time dashboard startup could run before Python setup finished | Open the dashboard after the runtime is verified |
| The install-readiness check could reset a running capture's status | Preserve the running status and require a verified runtime marker |
| Export could copy the ledger before the capture writer exited | Wait for shutdown before export and report copy failures |
| Forced power-off could damage a recently replaced journal/state file | Flushed writes, per-session recovery snapshots and last-good state backups |
| Skip was hidden and suggestions stopped after a short list | Visible control in idle/running states, persistent skips, catalog-guide fallback and no recorder restart |
| New users had no explicit upload choice | Uploads default off; manual Send and explicit auto-upload preference |
| Unpacked extension IDs varied by installation path | Fixed public manifest key and a derived expected extension ID |
| Every UI poll reread and transferred the entire catalog | File-stamp cache, conditional catalog requests and smaller progress responses |
| Existing tests depended on a personal recording | Synthetic record framing and isolated temporary profiles; no real packet fixture committed |
| A closed dashboard could miss a new export or retain an ambiguous sending state | Reconcile saved exports on startup; hold interrupted or recovered upload dispatches for server-status reconciliation |

## Validation

Windows CI runs native journal/recovery/bridge/stop-order tests, installs the pinned runtime into a fresh folder, checks source privacy patterns, validates PowerShell syntax, tests continuous tasks and skips, tests upload consent/deduplication, exercises a mocked Chrome connector, starts an isolated real HTTP service, and creates an allowlisted ZIP with checksums.

Native menu-input tests stub input and use process-identity checks; CI does not play New World, log into a game account, trigger disconnects or upload captures to Azoth. Interactive calibration and display-specific behavior require a user's local setup. The installer, package and clean-profile startup are checked separately from actual game compatibility.

No claim is made that an annotation proves a particular packet was collected, that automatic return defeats server checks, or that DX11 eliminates system freezes. The upstream collector's game-build support and account risks still apply. See the workflow result for the exact release commit rather than treating this document as a permanent green status.
