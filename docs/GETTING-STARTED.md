# Your first capture

Extract the Windows release into a folder you can write to, keep Steam signed in, and open `Start-Azoth.cmd`. Let the recorder's first-time setup finish. The dashboard opens automatically afterward. Use the native recorder's Browse button if the game path needs correcting.

Choose a wanted packet. The short starter list is followed by Azoth's other published guides. You can always choose a specific packet under **Choose a different capture**. A global Wanted status and your local attempt history are different: a packet can still be wanted after you tried it.

Click **Start this run**. The collector must launch the game to record it. If New World is already open without an active recording, close it normally first. Starting a new capture never silently closes an existing game.

Select your character. Once world entry is detected, follow the displayed action. Press F8 immediately after the action actually happens. You can instead select phone marking before starting and tap Done after each action.

**Next packet** advances after a completed checklist while keeping the same game and recording. **Skip this packet** advances when an action is unavailable, preserves any existing marks, and remembers the skip. Find a skipped target again using **Choose a different capture → All wanted**.

When done, **End session & send** stops recording, saves the files and checks the ZIP. The next target is selected independently of upload processing. If the page says **Review marks**, correct only what you remember; leave any uncertain action marked unsure. Review never changes original timestamps.

For manual sending, install the connector and press **Send to Azoth**, or download the ZIP and upload it on the website. For automatic sending, install the connector and enable the upload setting after reading the privacy note. **Uploaded** means sent for processing; **Accepted** is the project's final result.

## Phone

Use the same trusted home network. The URL and PIN are under **Settings → Use your phone**. A PIN is required on phones, but not in the desktop browser or upload extension. If necessary, run `Allow-Phone-Access.ps1` once as administrator to add the narrowly scoped firewall rule. Multiple network interfaces or a Public network can leave the app in desktop-only mode.

## Optional automatic return

Automatic return starts off. You can collect normally by selecting your character yourself after a disconnect.

To configure it, open **Settings → Set up automatic return**. On the character screen, select your character so Play is visible, then click **Set up character screen**. In each selection window, drag a tight rectangle around the requested heading, your character's name/world, and Play. Press Enter to accept each region, or C to cancel.

After an expected anti-cheat disconnect, click **Set up disconnect dialog**. Select the error heading, the specific expected reason, and the dismiss button. Do not calibrate a suspension or ban warning as an expected disconnect. Both screens must be saved before the enable checkbox becomes available.

The helper uses only these local images and normal mouse/key input, tied to the recorder-owned game process. Recalibrate if the display layout or UI scale changes. It stops on unknown screens, changed processes or account-warning evidence. It allows at most three returns within the recorder's session timeout. It does not bypass the disconnect or control movement/combat.

The corner guide is opened from Settings and can be closed with its X. Use borderless/windowed mode if the game hides desktop windows.
