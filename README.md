# Azoth Companion

An **unofficial Windows companion** for contributing New World packet recordings to [Project Azoth](https://projectazoth.com/). Pick a wanted packet, follow the guide, mark actions with F8 or your phone, and send a checked ZIP.

The dashboard, recorder integration, browser connector and source are in this repository. The capture implementation comes from [Azoth Capture](https://github.com/KyzaBOY/azoth-capture) and [Aeternum-World](https://github.com/Coldzer0/Aeternum-World). This project is not affiliated with Amazon or an official Azoth release.

**Account risk:** the upstream collector starts the game without Easy Anti-Cheat and instruments the game process. Disconnects are expected, and account safety cannot be guaranteed. This companion adds no anti-cheat bypass or kernel driver. Read the [upstream guidance](https://github.com/KyzaBOY/azoth-capture/blob/main/TUTORIAL.md#the-eac-situation-read-this) before collecting.

## Get started

1. Download the **Windows ZIP** from [Releases](https://github.com/n30nex/azoth-companion/releases), and extract it into a writable folder. Compare its SHA-256 with the release's `SHA256SUMS.txt` if you want to verify the download.
2. Keep Steam signed in. Double-click **Start-Azoth.cmd** as your normal Windows user. It finds New World in your Steam libraries or asks you to select `NewWorld.exe`.
3. Let the first-time runtime setup finish. You do **not** need to install Python, Git, Go or Node yourself. The recorder and local dashboard then open.
4. Choose a target and click **Start this run**. Select your character in the game. Follow the displayed action and press **F8 immediately after it happens**.
5. Use **Next packet** to keep the same recording, or **Skip this packet** if an action is unavailable. Skips also work before starting and are remembered.
6. Click **End session & send** to save and check the recording. Review uncertain marks. Use **Send to Azoth**, or download the ZIP and upload it on [Azoth's upload page](https://projectazoth.com/upload).

**Automatic uploads are off by default.** To enable them, install the optional connector below and turn on **Automatically send prepared captures to Azoth** in Settings. Captures contain account session data and are not anonymized. See [PRIVACY.md](PRIVACY.md).

Full instructions: [Getting started](docs/GETTING-STARTED.md) · [Troubleshooting](docs/TROUBLESHOOTING.md).

## What it does

- Shows Azoth's current wanted packets and source-provided instructions, with local attempt and skip history.
- Keeps one recording across multiple tasks, including preserved task boundaries and uncertain extra marks.
- Provides a phone-friendly LAN dashboard and an optional separate corner-guide window.
- Checks ledger framing, decoding, timestamps and ZIP contents. Only `ledger.bin` and `steps.json` go into upload ZIPs.
- Tracks waiting, uploaded, accepted, rejected and uncertain upload outcomes separately, with duplicate prevention by ledger hash.
- Uses DX11 when launching the game. It does not change graphics settings, drivers, game versions or disk locations.
- Flushes marker journals to disk and retains recovery snapshots and last-good companion state.
- Offers **optional, experimental** menu return after expected disconnects. Each user must calibrate their own character and disconnect screens. Gameplay and action marks remain manual.

An accepted ZIP does **not** prove a particular wanted packet was captured. Azoth's results determine points, newly captured packet types and first captures. The catalog's build number is a reference, not an acceptance allowlist.

## Optional upload connector

In Chrome, open Extensions, enable Developer mode, choose **Load unpacked**, and select `AzothCompanion/browser-connector` from the extracted release. Open its icon to check the connection, then sign in at `projectazoth.com/upload`.

There is **no connector PIN**. A fixed public extension key gives the unpacked extension a stable ID; the companion recognizes that ID on loopback. The extension's permissions cover only loopback and Project Azoth. It uses the signed-in upload page and does not export cookies. After upgrading the folder, click Reload in Chrome Extensions.

The connector's automatic transfer limit is 10 MiB per ZIP. Larger ZIPs can be downloaded and uploaded manually. Its upload endpoints are website integration points and can change; an uncertain response is held for inspection rather than blindly retried.

## Phone and corner guide

The desktop dashboard opens at `http://127.0.0.1:8877` without a PIN. In **Settings → Use your phone**, find the LAN address and the randomly generated phone PIN.

Phone access requires one trusted Windows **Private** home-network connection. If the firewall blocks it, run `AzothCompanion/Allow-Phone-Access.ps1` once as administrator. This creates an application-, address-, subnet- and Private-profile-limited rule. No router configuration, public hosting, startup task or Windows service is installed.

The corner guide is an ordinary topmost desktop window; borderless/windowed game mode may be needed. It does not inject an overlay into the game.

## Data and updates

Settings, phone credentials, journals, templates, prepared ZIPs and upload receipts live under `%LOCALAPPDATA%\AzothCompanion`. Exported capture folders default to `Documents\Azoth Captures`. Raw engine recordings and downloaded dependencies live beside the recorder in the extracted `AzothCapture` folder. **That folder is sensitive; do not publish it.**

For an update, finish the recording, close the recorder and run `AzothCompanion/Stop-Companion.ps1`. Extract the new release over the program files, keeping the existing runtime and captures. The per-user profile remains separate. Reload the Chrome extension afterward. Do not run two recorder copies at once.

No recordings, personal menu images, account information, saved PINs or credentials are included in the repository or release ZIP.

## Build and verify

Windows 10/11 x64 with the Microsoft Edge WebView2 runtime is required. For development, install Go matching `recorder/go.mod`, Python 3.12+ and Node.js.

```powershell
cd recorder
go test ./...
go install github.com/wailsapp/wails/v2/cmd/wails@v2.13.0
wails build -platform windows/amd64 -trimpath -o AzothCapture.Companion.exe
cd ..
python scripts/package_release.py --exe recorder/build/bin/AzothCapture.Companion.exe
```

[Windows CI](https://github.com/n30nex/azoth-companion/actions) performs a fresh runtime installation, native tests, synthetic capture validation, connector checks, clean-profile HTTP checks and packaging. Game login and real uploads are not performed in CI. The exact source commit and recorder checksum are included in each bundle's `BUILD-INFO.json`.

See the [audit and validation notes](docs/AUDIT.md), [security policy](SECURITY.md), [release notes](CHANGELOG.md) and [component notices](NOTICE.md). Contributions and bug reports are welcome; remove recordings, credentials and personal menu images before attaching anything.

## License

Companion code and supporting scripts: **AGPL-3.0-only**. The integrated recorder under `recorder/` retains its **MIT** license and upstream notices. Downloaded dependencies retain their own licenses. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
