# Configuration Raspberry Pi — Serveur central

## Matériel
- **Modèle** : Raspberry Pi 3
- **OS** : Raspberry Pi OS Lite 64-bit (Bookworm, Dec 2025)
- **Carte SD** : 8 GB
- **Alimentation** : 5V / 2.5A micro-USB
- **Accès réseau** : Wi-Fi + Ethernet
- **IP locale** : 192.168.2.72
- **Hostname** : `raspberry`
- **Utilisateur** : `pi`

## Accès SSH
```bash
ssh pi@raspberry.local
```

---

## Vue d'ensemble des projets

| Projet | Repo GitHub | Dossier Pi | Repo local Mac | Services |
|--------|------------|------------|----------------|----------|
| strava-dashboard | seb-tester/strava-dashboard | `/home/pi/strava/` | `OneDrive/Claude/strava-dashboard` | strava-webhook, strava-sync.timer |
| briefing-system | seb-tester/briefing-system | `/home/pi/briefing/` | `OneDrive/Claude/git_briefing-system` | briefing-daily.timer, briefing-weekly.timer |

### Infrastructure partagée
- **`cloudflared`** — tunnel public unique, expose le port 8000 sur `*.trycloudflare.com`
- **`strava-webhook` (FastAPI)** — gère les webhooks des DEUX projets :
  - `/webhook` → événements Strava
  - `/deploy` → auto-deploy de strava-dashboard
  - `/deploy-briefing` → auto-deploy de briefing-system

### Carte d'intégration
```
GitHub (strava-dashboard)  ──POST /deploy──────────┐
GitHub (briefing-system)   ──POST /deploy-briefing──┤
Strava API                 ──POST /webhook──────────┴──▶  strava-webhook (FastAPI :8000)
                                                              │
                                    cloudflared tunnel ───────┘
                                    URL: https://xxxxx.trycloudflare.com

briefing-daily.timer  (23h00)  ──▶  briefing_daily.py  ──▶  Gmail
briefing-weekly.timer (dim 10h) ──▶  briefing_weekly.py ──▶  Gmail
                                          │
                                    Google Calendar API
```

---

## Projet 1 — strava-dashboard

### Structure des dossiers
```
/home/pi/strava/
├── venv/                  # Environnement virtuel Python
├── strava_sync.py         # Agent de sync Strava
├── strava_dashboard.py    # Générateur de dashboard HTML
├── webhook.py             # Serveur FastAPI (webhooks Strava + déploiement GitHub)
├── strava_token.json      # Token OAuth Strava
├── strava_last_sync.json  # Timestamp de la dernière sync
├── strava_sync.log        # Logs de la sync
└── strava_output/
    ├── activites.csv      # Base de données des activités
    └── dashboard.html     # Dashboard HTML généré
```

### Services systemd

**strava-webhook** (FastAPI sur port 8000)
```
/etc/systemd/system/strava-webhook.service
```
- Démarre automatiquement au boot
- Gère les webhooks Strava et les déploiements GitHub (strava + briefing)
- Sert le dashboard HTML sur `/`

**cloudflared** (tunnel public)
```
/etc/systemd/system/cloudflared.service
```
- Expose le port 8000 sur une URL publique trycloudflare.com
- ⚠️ **L'URL change à chaque redémarrage** — voir section "Après un redémarrage"

**strava-sync.timer** (sync horaire)
```
/etc/systemd/system/strava-sync.service
/etc/systemd/system/strava-sync.timer
```
- Déclenche `strava_sync.py` toutes les heures

### Mise à jour via Git
```bash
cd ~/strava && git pull origin main
sudo systemctl restart strava-webhook
```

### Commandes utiles
```bash
# Statut
sudo systemctl status strava-webhook cloudflared strava-sync.timer

# Logs en temps réel
sudo journalctl -u strava-webhook -f

# Redémarrer
sudo systemctl restart strava-webhook

# Régénérer le dashboard manuellement
cd ~/strava && source venv/bin/activate && python3 strava_dashboard.py

# Sync complète depuis 2018
cd ~/strava && source venv/bin/activate && python3 strava_sync.py --full

# Supprimer une activité du CSV par ID
cd ~/strava && source venv/bin/activate && python3 strava_sync.py --delete-activity-id ID
```

### Endpoints FastAPI
| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Dashboard HTML |
| `/webhook` | GET | Validation webhook Strava |
| `/webhook` | POST | Réception événements Strava |
| `/deploy` | POST | Déploiement automatique strava-dashboard |
| `/deploy-briefing` | POST | Déploiement automatique briefing-system |

### API Strava
- **Client ID** : 212809
- **Client Secret** : ac7d4e9a7a33e4ced25c3ed01fcf90e435ebec26
- **Webhook Verify Token** : `strava_webhook_token`
- **Dernier Webhook ID Strava** : 336772 ← ⚠️ mettre à jour après chaque redémarrage

---

## Projet 2 — briefing-system

### Structure des dossiers
```
/home/pi/briefing/
├── venv/                   # Environnement virtuel Python
├── briefing_daily.py       # Envoi briefing quotidien
├── briefing_weekly.py      # Envoi récap hebdomadaire
├── briefing_html.py        # Génération HTML des emails
├── briefing_utils.py       # Fonctions partagées
├── briefing_config.json    # Configuration (emails, météo, calendriers)
├── gcal_credentials.json   # OAuth Google Calendar (ne pas committer)
├── gcal_token.json         # Token Google Calendar (ne pas committer)
└── briefing.log            # Logs
```

### Services systemd

**briefing-daily.timer** — tous les jours à 23h00 (envoi même si agenda vide)
```
/etc/systemd/system/briefing-daily.service
/etc/systemd/system/briefing-daily.timer
```
- Envoie le briefing du lendemain matin (météo, agenda, tâches)
- ⚠️ Le briefing cible `date.today() + 1` — toutes les données (calendrier, NHL, CFL, NFL) sont fetched pour le lendemain, pas pour le jour de génération

**briefing-weekly.timer** — dimanche à 10h00
```
/etc/systemd/system/briefing-weekly.service
/etc/systemd/system/briefing-weekly.timer
```
- Envoie le récap hebdomadaire

### Mise à jour via Git
```bash
cd ~/briefing && git pull origin main
# Pas de redémarrage de service requis (timers oneshot)
# Les timers reprennent automatiquement au prochain déclenchement
```

### Commandes utiles
```bash
# Statut des timers
sudo systemctl status briefing-daily.timer briefing-weekly.timer

# Prochain déclenchement
systemctl list-timers briefing-daily.timer briefing-weekly.timer

# Logs
sudo journalctl -u briefing-daily -f
sudo journalctl -u briefing-weekly -f

# Test manuel (génère un HTML sans envoyer)
cd ~/briefing && source venv/bin/activate
python3 briefing_daily.py --test    # → /tmp/briefing_test_daily.html
python3 briefing_weekly.py --test   # → /tmp/briefing_test_weekly.html

# Envoi manuel forcé
cd ~/briefing && source venv/bin/activate
python3 briefing_daily.py
```

### Secrets et config
| Clé | Valeur / Emplacement |
|-----|---------------------|
| Gmail user | gravel.sebastien@gmail.com |
| Gmail app password | jbmgixfsvmdottlw |
| Google Calendar credentials | `/home/pi/briefing/gcal_credentials.json` |
| Config principale | `/home/pi/briefing/briefing_config.json` |

---

## Ports utilisés
| Port | Service |
|------|---------|
| 22   | SSH |
| 8000 | FastAPI strava-webhook (interne) |

## Secrets partagés
| Clé | Valeur |
|-----|--------|
| GitHub deploy secret (strava) | `strava_deploy_secret` |
| Strava verify token | `strava_webhook_token` |

---

## ⚠️ Après un redémarrage du Pi

### Étape 1 — Récupérer la nouvelle URL Cloudflare
```bash
sudo journalctl -u cloudflared | grep trycloudflare.com | tail -1
```
Copier l'URL (format : `https://xxxxx-xxxxx-xxxxx.trycloudflare.com`)

### Étape 2 — Mettre à jour le webhook GitHub (strava-dashboard)
1. Aller sur `github.com/seb-tester/strava-dashboard` → Settings → Webhooks
2. Remplacer le Payload URL par : `https://NOUVELLE_URL.trycloudflare.com/deploy`
3. Cliquer "Update webhook"

### Étape 3 — Mettre à jour le webhook GitHub (briefing-system)
1. Aller sur `github.com/seb-tester/briefing-system` → Settings → Webhooks
2. Remplacer le Payload URL par : `https://NOUVELLE_URL.trycloudflare.com/deploy-briefing`
3. Cliquer "Update webhook"

### Étape 4 — Mettre à jour le webhook Strava
```bash
# Supprimer l'ancien (remplacer WEBHOOK_ID par la valeur ci-dessus)
curl -X DELETE "https://www.strava.com/api/v3/push_subscriptions/WEBHOOK_ID?client_id=212809&client_secret=ac7d4e9a7a33e4ced25c3ed01fcf90e435ebec26"

# Enregistrer le nouveau
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=212809 \
  -F client_secret=ac7d4e9a7a33e4ced25c3ed01fcf90e435ebec26 \
  -F callback_url=https://NOUVELLE_URL.trycloudflare.com/webhook \
  -F verify_token=strava_webhook_token
```
⚠️ **Noter le nouvel ID retourné** et mettre à jour "Dernier Webhook ID Strava" dans ce fichier !

### Étape 5 — Vérifier que tout tourne
```bash
sudo systemctl status strava-webhook cloudflared strava-sync.timer briefing-daily.timer briefing-weekly.timer
```

---

## Workflow de déploiement (push → Pi)

```
Mac : git add . && git commit -m "..." && git push
  ↓
GitHub envoie POST /deploy (ou /deploy-briefing)
  ↓
Pi : git pull → redémarre le service si nécessaire
```

Le redémarrage automatique est géré par `webhook.py` pour strava-dashboard.
Pour briefing-system, le `git pull` suffit (les timers sont oneshot).

---

## Environnement Python
```bash
# strava-dashboard
cd ~/strava && source venv/bin/activate

# briefing-system
cd ~/briefing && source venv/bin/activate
```

## Commandes de maintenance générales
```bash
# Voir l'espace disque
df -h

# Vérifier la température du Pi
vcgencmd measure_temp

# Voir tous les services actifs
sudo systemctl list-units --type=service --state=running

# Voir tous les timers
systemctl list-timers
```

---

## Améliorations futures
- **Domaine fixe** : Acheter un domaine sur Cloudflare (~10$/an) → URL fixe, plus jamais de reconfiguration post-reboot
- **Cloudflare Tunnel avec compte** : Tunnel nommé et persistant avec un domaine fixe
- **Nginx** : Reverse proxy pour servir le dashboard sur le port 80/443 directement
