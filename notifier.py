"""
notifier.py — Notifications push via ntfy.sh
Utilisé par strava_sync.py et webhook.py
"""

import urllib.request

# ══════════════════════════════════════════════════════════
#  CONFIG — choisir un topic unique (c'est votre "canal")
#  Installer l'app ntfy sur iPhone et s'abonner à ce topic
NTFY_TOPIC = "seb-pi-notif"
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}"
# ══════════════════════════════════════════════════════════


def notify(title, message, priority="default", tags=None):
    """
    Envoie une notification push via ntfy.sh

    priority : "min" | "low" | "default" | "high" | "urgent"
    tags     : liste d'emoji/mots-clés, ex. ["muscle", "warning"]
               voir https://docs.ntfy.sh/emojis/
    """
    try:
        headers = {
            "Title": title,
            "Priority": priority,
            "Content-Type": "text/plain; charset=utf-8",
        }
        if tags:
            headers["Tags"] = ",".join(tags)

        req = urllib.request.Request(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"⚠️  Notification ntfy échouée : {e}")
