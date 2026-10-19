# Troubleshooting

**First setup has not opened the dashboard:** watch the recorder's Activity Log. Downloads and package installation must finish first. If setup failed, use its Install control to retry, then reopen `Start-Azoth.cmd`. Use a normal Windows account and a writable extracted folder.

**Steam must be running:** open Steam and sign in before starting. The companion does not sign in for you.

**Game already open:** a fresh capture needs the collector to launch the game. Close it normally, then start. During an active recording, use Next or Skip to keep collecting without a restart.

**Expected disconnect:** it is separate from a Windows crash. Select your character manually, or configure and enable automatic return. A return can spend time on loading screens. The dashboard distinguishes loading, returning and world entry. After three automatic returns, the session is saved instead of looping indefinitely.

**Automatic return stops:** check the displayed error. Recalibrate the character and expected-disconnect regions if the UI scale, resolution or layout changed. Never calibrate an account restriction as an expected disconnect. Manual selection remains available.

**PC freeze or lost power:** do not overwrite or delete the raw capture. Open the recorder and use its recovered-draft prompt, then stop/export that recovered session. Journals are flushed and snapshots tolerate damaged draft files, but hardware or power loss can still lose data. Do not invent missing marker times. A diagnostic report should exclude account data.

**Still waiting to upload:** open the connector icon, sign in on the upload page, and check whether automatic uploads are enabled or the capture was explicitly sent. Review uncertain marks first. Larger than 10 MiB ZIPs use manual upload. Unknown upload outcomes are not automatically retried; inspect My uploads first to avoid duplicates.

**Catalog build differs:** it is a reference value, not proof that Azoth will reject your client. Consult the current project guidance. This package does not downgrade or patch the game.

**Slow game:** this launcher uses DX11. Adjust the game's graphics and frame cap for your hardware and close unused applications yourself. It does not relocate the game, change drivers, modify pagefiles or alter graphics settings.

**Phone cannot connect:** use the current URL in Settings, a single trusted Private network, and the same Wi-Fi. Run the included firewall helper if required. No port forwarding is needed. Do not expose the dashboard on the Internet.

**Upgrading:** finish the capture, close the recorder and stop the dashboard before replacing files. Keep the runtime/capture folder and per-user profile. Reload the unpacked extension in Chrome. A different recorder copy already running is left untouched.
