# What stays local and what is sent

The default is local collection and preparation. Automatic uploading starts **off**. You can send a prepared recording explicitly, or turn on automatic uploads in Settings. Turning the setting off prevents future automatic dispatches; an upload already in progress may finish.

Upload ZIPs contain exactly `ledger.bin` and `steps.json`. The ledger is plaintext game-session traffic and is **not anonymized**. It can contain account/session data, including voice-service data. The journal contains your activity descriptions and times. Share them only with a destination you trust.

Raw engine folders may also contain HTTPS logs and TLS keys. Those files are excluded from prepared ZIPs. Never publish the raw capture folder, the runtime folder, `%LOCALAPPDATA%\AzothCompanion`, or screenshots of your local pairing settings.

The companion reads Project Azoth's public packet catalog and rankings. Requests use ordinary HTTPS; the site sees the requesting IP and application user agent. Catalog requests use ETags when supplied. No added analytics service or cloud storage is used.

The optional extension contacts only `127.0.0.1` and `projectazoth.com`. It obtains prepared ZIPs from the local upload-only API and submits them through the signed-in Azoth upload page. It reads upload results to reconcile status and avoid duplicates. Authentication cookies stay in the browser; the extension has no cookies permission.

Character names and world labels you enter are local preferences. Menu calibration saves only the selected regions under the local profile. Those images are not included in uploads or release packages. Automatic return is off until both screens are configured and you enable it.

The dashboard serves HTTP on loopback and, when available, one Private home-network address. Phone access uses a random PIN and session cookie. Use it only on a trusted home network; HTTP does not protect traffic from another device monitoring that network. The listener is not a public Internet service.

Removing the application folder does not delete exported captures or the per-user profile. Keep any recordings you want before removing them yourself. `Stop-Companion.ps1` stops only the dashboard, not the game or recorder.
