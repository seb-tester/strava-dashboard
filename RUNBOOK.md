# RUNBOOK — strava-dashboard

**Repo** : `github.com/seb-tester/strava-dashboard`
**Dossier Pi** : `/home/pi/strava/`
**Doc complète** : `raspberry-pi-config.md` dans le dossier Claude

---

## Mise à jour via Git

```bash
cd ~/strava && git pull origin main
sudo systemctl restart strava-webhook
```

> Le push depuis le Mac déclenche automatiquement un déploiement via le webhook GitHub → `/deploy`

---

## Services

| Service | Rôle |
|---------|------|
| `strava-webhook` | FastAPI port 8000 — webhooks Strava + auto-deploy des 2 projets |
| `cloudflared` | Tunnel public (URL change au reboot ⚠️) |
| `strava-sync.timer` | Sync horaire des activités Strava |

```bash
# Statut
sudo systemctl status strava-webhook cloudflared strava-sync.timer

# Redémarrer le serveur
sudo systemctl restart strava-webhook

# Logs en temps réel
sudo journalctl -u strava-webhook -f
```

---

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard HTML |
| `GET/POST /webhook` | Webhook Strava (validation + événements) |
| `POST /deploy` | Auto-deploy strava-dashboard depuis GitHub |
| `POST /deploy-briefing` | Auto-deploy briefing-system depuis GitHub |

---

## Après un redémarrage du Pi

L'URL Cloudflare change — il faut mettre à jour 3 webhooks.
Voir la procédure complète dans `raspberry-pi-config.md` → section "Après un redémarrage".

```bash
# 1. Trouver la nouvelle URL
sudo journalctl -u cloudflared | grep trycloudflare.com | tail -1

# 2. Mettre à jour le webhook Strava
curl -X DELETE "https://www.strava.com/api/v3/push_subscriptions/WEBHOOK_ID?client_id=212809&client_secret=ac7d4e9a7a33e4ced25c3ed01fcf90e435ebec26"
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=212809 \
  -F client_secret=ac7d4e9a7a33e4ced25c3ed01fcf90e435ebec26 \
  -F callback_url=https://NOUVELLE_URL.trycloudflare.com/webhook \
  -F verify_token=strava_webhook_token
# ⚠️ Noter le nouvel ID retourné dans raspberry-pi-config.md

# 3. Mettre à jour les 2 webhooks GitHub (Settings → Webhooks sur chaque repo)
#    strava-dashboard : https://NOUVELLE_URL.trycloudflare.com/deploy
#    briefing-system  : https://NOUVELLE_URL.trycloudflare.com/deploy-briefing
```

---

## Dépendances inter-projets

- Ce service (`strava-webhook`) gère aussi le déploiement de **briefing-system** via `/deploy-briefing`
- Les deux projets partagent le même tunnel **cloudflared**

---

## Commandes utiles

```bash
# Régénérer le dashboard manuellement
cd ~/strava && source venv/bin/activate && python3 strava_dashboard.py

# Sync complète depuis 2018
cd ~/strava && source venv/bin/activate && python3 strava_sync.py --full

# Supprimer une activité par ID
cd ~/strava && source venv/bin/activate && python3 strava_sync.py --delete-activity-id ID
```
