#!/bin/bash
# notify_failure.sh — Envoi une notification ntfy quand un service systemd plante
# Usage : appelé automatiquement par systemd via OnFailure=notify-failure@%n.service
#
# Déploiement sur le Pi :
#   sudo cp notify_failure.sh /home/pi/strava/notify_failure.sh
#   sudo chmod +x /home/pi/strava/notify_failure.sh

NTFY_TOPIC="seb-pi-notif"
SERVICE="$1"

curl -s -X POST "https://ntfy.sh/${NTFY_TOPIC}" \
    -H "Title: 🚨 Service planté : ${SERVICE}" \
    -H "Priority: urgent" \
    -H "Tags: warning,rotating_light" \
    -d "Le service '${SERVICE}' s'est arrêté sur le Pi.

Diagnostiquer :
  sudo journalctl -u ${SERVICE} -n 50
  sudo systemctl status ${SERVICE}"
