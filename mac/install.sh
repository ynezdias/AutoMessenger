#!/bin/zsh
# AutoMessenger Mac mini installer.
# Run from inside the copied AutoMessenger folder:   zsh mac/install.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Project folder: $ROOT"

# 1. Ollama must be installed first (https://ollama.com/download/mac).
if ! command -v ollama >/dev/null 2>&1; then
  echo "STOP: install Ollama first from https://ollama.com/download/mac,"
  echo "open the app once, then re-run this script."
  exit 1
fi

# 2. The model (skips instantly if already downloaded).
ollama pull llama3.1:8b

# 3. The one Python dependency.
/usr/bin/python3 -m pip install --user --quiet boto3

# 4. Settings file must have come over from the Windows machine.
if [ ! -f "$ROOT/server/.env" ]; then
  echo "STOP: server/.env is missing. Copy it from the Windows machine"
  echo "(it holds the AWS keys and the upload link), then re-run."
  exit 1
fi

# 5. Install both services so macOS starts them at login and revives them on
#    crash. launchd replaces run.ps1, watchdog.ps1, and the Startup shortcut.
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
for name in worker webchat; do
  plist="$HOME/Library/LaunchAgents/com.automessenger.$name.plist"
  sed "s|__ROOT__|$ROOT|g" "$ROOT/mac/com.automessenger.$name.plist" > "$plist"
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist"
done

echo ""
echo "Done. Both services are running and will start on every login."
echo "Watch the worker:   tail -f \"$ROOT/logs/worker.log\""
echo "Chat page:          http://localhost:8765"
echo ""
echo "Still recommended (one time, in System Settings or Terminal):"
echo "  sudo pmset -a sleep 0          # never sleep"
echo "  sudo pmset -a autorestart 1    # power back on after an outage"
echo "  System Settings -> Users -> enable automatic login for this user"
echo "  System Settings -> General -> Date & Time: set your business timezone"
echo "  Ollama menu bar icon -> Settings: start at login"
