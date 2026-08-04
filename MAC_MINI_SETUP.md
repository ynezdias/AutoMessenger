# Moving AutoMessenger to the Mac mini

Only the "brain" moves. AWS (queues, Lambdas, database, alerts) and the
Salesforce side stay exactly as they are and will not notice the handover.
Total time: about an hour, most of it the model download.

## On the Mac mini

1. **Install Ollama**: download from https://ollama.com/download/mac, drag to
   Applications, open it once. In its menu-bar settings, enable "start at
   login".
2. **Copy the project folder** `AutoMessenger` from the Windows machine to the
   mini (AirDrop, USB stick, or network share). Make sure `server/.env` came
   with it — it is the file with the AWS keys and upload link. If you copy via
   git instead, `.env` is deliberately not in git and must be moved by hand.
3. **Run the installer** in Terminal:
   ```sh
   cd ~/AutoMessenger        # wherever you put the folder
   zsh mac/install.sh
   ```
   It downloads the model, installs the one Python dependency, and registers
   both services with macOS so they start at every login and restart within
   seconds if they ever crash (this replaces run.ps1, watchdog.ps1, and the
   Windows Startup shortcut — none of those are used on the Mac).
4. **One-time machine settings** (the installer prints these too):
   ```sh
   sudo pmset -a sleep 0          # the mini never sleeps
   sudo pmset -a autorestart 1    # boots itself after a power outage
   ```
   Then in System Settings: enable **automatic login** for this user (so the
   services start after an unattended reboot), and set **Date & Time** to your
   business timezone — the follow-up quiet hours (9:00 to 19:00) follow the
   machine's clock.
5. **Test it**: open http://localhost:8765 and text Walter, or watch
   `tail -f logs/worker.log` while a test message goes through the webhook.

## On the Windows machine (the handover)

Only one worker may poll the queue at a time. Once the mini is confirmed
running:

```powershell
schtasks /Delete /TN "AutoMessengerWatchdog" /F
Remove-Item "$([Environment]::GetFolderPath('Startup'))\AutoMessenger.cmd"
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "server\.(main|webchat)|run\.ps1" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

That deletes the watchdog task, the login shortcut, and stops the running
processes. The laptop is now just a laptop; the mini owns the job.

## Before go-live (not Mac-specific, but do not miss it)

- `FOLLOWUP_ENABLED=0` in `server/.env` right now. The conversations table
  still contains test rows from development, one of which is a real phone
  number saved under a test name. Clear those rows, then set the flag to 1.
- `python -m server.followup --dry-run` lists exactly who would be nudged.
  Run it once after clearing, confirm the list is empty, then enable.

## Notes

- Conversation history is in AWS, not on either machine, so nothing about the
  merchants moves or is lost. The only local state is the practice-page
  sandbox file (`server/.local_conversations.json`) — copy it if you want the
  test threads, skip it if you don't.
- Apple-silicon Macs run this model with GPU acceleration; expect faster
  replies than the Windows laptop.
- If the mini ever has both services down and you cannot reach it, the AWS
  mailbox quietly holds every unanswered text for up to 4 days.
- The Cloudflare tunnel (if you still use it for the chat page) needs
  cloudflared installed on the mini and pointed at http://localhost:8765,
  same as before.
