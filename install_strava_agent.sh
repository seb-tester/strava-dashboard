#!/bin/bash
# ─────────────────────────────────────────────────────────
#  Strava Agent — Installation macOS (LaunchAgent)
#  Lance strava_sync.py automatiquement toutes les heures
# ─────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=$(which python3 || which python)
PLIST_NAME="com.user.strava-sync"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "📍 Dossier du script : $SCRIPT_DIR"
echo "🐍 Python : $PYTHON"

# Créer le fichier plist
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$SCRIPT_DIR/strava_sync.py</string>
    </array>

    <key>StartInterval</key>
    <integer>3600</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/strava_sync.log</string>

    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/strava_sync_error.log</string>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
</dict>
</plist>
EOF

# Charger l'agent
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo ""
echo "✅ Agent Strava installé et démarré !"
echo "   → Sync automatique toutes les heures"
echo "   → Logs : $SCRIPT_DIR/strava_sync.log"
echo ""
echo "Commandes utiles :"
echo "  Arrêter  : launchctl unload ~/Library/LaunchAgents/$PLIST_NAME.plist"
echo "  Relancer : launchctl load   ~/Library/LaunchAgents/$PLIST_NAME.plist"
echo "  Voir logs: tail -f $SCRIPT_DIR/strava_sync.log"
