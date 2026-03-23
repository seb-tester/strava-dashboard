"""
Strava Sync — Agent horaire
Vérifie les nouvelles activités Strava, met à jour les graphiques et envoie un email résumé.

Configuration :
  1. Remplis les variables dans la section CONFIG ci-dessous
  2. Lance install_strava_agent.sh pour programmer l'exécution automatique toutes les heures
"""

import requests
import json
import os
import time
import smtplib
import csv
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, timezone

# ════════════════════════════════════════════════════════
#  CONFIG — À remplir
# ════════════════════════════════════════════════════════
CLIENT_ID     = "212809"
CLIENT_SECRET = "ac7d4e9a7a33e4ced25c3ed01fcf90e435ebec26"
GMAIL_USER    = "gravel.sebastien@gmail.com"
GMAIL_APPPASS = "jbmgixfsvmdottlw"              # mot de passe app Gmail
EMAIL_DEST    = "gravel.sebastien@gmail.com"
# ════════════════════════════════════════════════════════

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE  = os.path.join(SCRIPT_DIR, "strava_token.json")
CSV_FILE    = os.path.join(SCRIPT_DIR, "strava_output", "activites.csv")
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "strava_output")
LOG_FILE    = os.path.join(SCRIPT_DIR, "strava_sync.log")

SPORT_LABELS = {
    "Run": "Course", "Ride": "Vélo", "Swim": "Natation",
    "Walk": "Marche", "Hike": "Randonnée", "VirtualRide": "Vélo virtuel",
    "VirtualRun": "Course virtuelle", "WeightTraining": "Musculation",
}

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Token ──────────────────────────────────────────────
def get_access_token():
    if not os.path.exists(TOKEN_FILE):
        log("❌ Fichier token introuvable. Lance strava_analyse.py d'abord pour t'authentifier.")
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        token = json.load(f)
    if token.get("expires_at", 0) > time.time() + 60:
        return token["access_token"]
    log("🔄 Rafraîchissement du token...")
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"]
    })
    new_token = resp.json()
    if "access_token" not in new_token:
        log(f"❌ Erreur refresh token: {new_token}")
        sys.exit(1)
    with open(TOKEN_FILE, "w") as f:
        json.dump(new_token, f)
    return new_token["access_token"]

# ── Suivi du dernier sync ──────────────────────────────
LAST_SYNC_FILE = os.path.join(SCRIPT_DIR, "strava_last_sync.json")

def get_last_sync_timestamp():
    """Retourne le timestamp du dernier sync (ou 7 jours en arrière si premier sync)."""
    if os.path.exists(LAST_SYNC_FILE):
        with open(LAST_SYNC_FILE) as f:
            data = json.load(f)
        return data.get("last_sync", time.time() - 7 * 24 * 3600)
    return time.time() - 7 * 24 * 3600

def save_last_sync_timestamp(email_sent_today=False):
    data = {"last_sync": time.time()}
    if os.path.exists(LAST_SYNC_FILE):
        with open(LAST_SYNC_FILE) as f:
            existing = json.load(f)
        data["last_daily_summary"] = existing.get("last_daily_summary", "")
    if email_sent_today:
        data["last_daily_summary"] = datetime.now().strftime("%Y-%m-%d")
    with open(LAST_SYNC_FILE, "w") as f:
        json.dump(data, f)

def should_send_daily_summary():
    """Retourne True si on doit envoyer le résumé journalier (après 20h, pas encore envoyé aujourd'hui)."""
    if datetime.now().hour < 20:
        return False
    if not os.path.exists(LAST_SYNC_FILE):
        return True
    with open(LAST_SYNC_FILE) as f:
        data = json.load(f)
    last = data.get("last_daily_summary", "")
    return last != datetime.now().strftime("%Y-%m-%d")

# ── Activités existantes ───────────────────────────────
def load_existing_ids():
    """Charge les IDs existants depuis le CSV (colonne 'id' si disponible)."""
    ids = set()
    if not os.path.exists(CSV_FILE):
        return ids
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "id" in row and row["id"].strip('"'):
                ids.add(row["id"].strip('"'))
    return ids

# ── Nouvelles activités ────────────────────────────────
def fetch_recent_activities(token, after_timestamp):
    activities = []
    page = 1
    while True:
        resp = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 50, "page": page, "after": int(after_timestamp)}
        )
        batch = resp.json()
        if not batch or not isinstance(batch, list):
            break
        activities.extend(batch)
        if len(batch) < 50:
            break
        page += 1
    return activities

def activity_to_row(a):
    sport = a.get("type", "Autre")
    return {
        "id":          str(a.get("id", "")),
        "date":        a.get("start_date_local", "")[:19].replace("T", " "),
        "sport":       SPORT_LABELS.get(sport, sport),
        "nom":         a.get("name", ""),
        "distance_km": round(a.get("distance", 0) / 1000, 2),
        "duree_min":   round(a.get("moving_time", 0) / 60, 1),
        "denivele_m":  round(a.get("total_elevation_gain", 0), 0),
        "vitesse_moy": round(a.get("average_speed", 0) * 3.6, 2),
        "fc_moy":      a.get("average_heartrate", ""),
        "calories":    a.get("kilojoules", ""),
    }

def append_to_csv(new_activities):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fieldnames = ["id","date","sport","nom","distance_km","duree_min","denivele_m","vitesse_moy","fc_moy","calories"]
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        if not file_exists:
            writer.writeheader()
        for a in new_activities:
            writer.writerow(activity_to_row(a))

# ── Graphiques ─────────────────────────────────────────
def regenerate_graphs():
    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        df = pd.read_csv(CSV_FILE, encoding="utf-8-sig", on_bad_lines="skip")
        df["date"] = pd.to_datetime(df["date"])
        df["mois"] = df["date"].dt.to_period("M")
        df["annee"] = df["date"].dt.year
        COULEURS = ["#FC4C02", "#4A90D9", "#27AE60", "#F39C12"]

        # Graphique 1 : Distance mensuelle
        sports = ["Course", "Vélo"]
        df_sport = df[df["sport"].isin(sports)]
        if not df_sport.empty:
            pivot = df_sport.groupby(["mois", "sport"])["distance_km"].sum().unstack(fill_value=0)
            pivot.index = pivot.index.to_timestamp()
            fig, ax = plt.subplots(figsize=(14, 5))
            bottom = None
            for i, col in enumerate(pivot.columns):
                ax.bar(pivot.index, pivot[col], label=col, color=COULEURS[i], bottom=bottom, width=20)
                bottom = pivot[col] if bottom is None else bottom + pivot[col]
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            plt.xticks(rotation=45, ha="right")
            ax.set_ylabel("Distance (km)")
            ax.set_title("Distance mensuelle par sport", fontsize=14, fontweight="bold")
            ax.legend(); ax.grid(axis="y", alpha=0.3)
            fig.savefig(os.path.join(OUTPUT_DIR, "02_km_par_mois.png"), dpi=150, bbox_inches="tight")
            plt.close(fig)

        # Graphique 2 : Progression annuelle
        df_run = df[df["sport"] == "Course"]
        if not df_run.empty:
            yearly = df_run.groupby("annee")["distance_km"].sum()
            fig, ax = plt.subplots(figsize=(9, 5))
            bars = ax.bar(yearly.index.astype(str), yearly.values, color="#FC4C02")
            for bar, val in zip(bars, yearly.values):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                        f"{val:.0f} km", ha="center", fontsize=10, fontweight="bold")
            ax.set_ylabel("Distance totale (km)")
            ax.set_title("Progression annuelle — Course à pied", fontsize=14, fontweight="bold")
            ax.grid(axis="y", alpha=0.3)
            fig.savefig(os.path.join(OUTPUT_DIR, "03_progression_annuelle.png"), dpi=150, bbox_inches="tight")
            plt.close(fig)

        log("📈 Graphiques mis à jour.")
    except Exception as e:
        log(f"⚠️  Erreur graphiques : {e}")

# ── Dashboard ─────────────────────────────────────────
def regenerate_dashboard():
    try:
        import subprocess
        dashboard_script = os.path.join(SCRIPT_DIR, "strava_dashboard.py")
        if os.path.exists(dashboard_script):
            subprocess.run(["python3", dashboard_script], check=True,
                           capture_output=True)
            log("🌐 Dashboard HTML mis à jour.")
        else:
            log("⚠️  strava_dashboard.py introuvable, dashboard non mis à jour.")
    except Exception as e:
        log(f"⚠️  Erreur dashboard : {e}")

# ── Email ──────────────────────────────────────────────
def format_duration(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h}h{m:02d}" if h else f"{m} min"

def build_goals_html_email():
    """Génère le bloc HTML des goals pour l'email."""
    GOALS = {
        "Vélo":   {"km": 2050, "annee": 2026},
        "Course": {"km": 560,  "annee": 2026},
    }
    try:
        import pandas as pd
        from datetime import datetime, timedelta
        df = pd.read_csv(CSV_FILE, encoding="utf-8-sig", on_bad_lines="skip")
        df["date"]        = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
        df["annee"]       = df["date"].dt.year
        df["distance_km"] = pd.to_numeric(df["distance_km"], errors="coerce").fillna(0)

        today      = datetime.now()
        day_of_yr  = today.timetuple().tm_yday
        days_total = 366 if today.year % 4 == 0 else 365
        days_left  = days_total - day_of_yr

        html = """<div style="margin-top:20px">
          <h3 style="color:#FC4C02;margin-bottom:12px">🎯 Progression vers les goals</h3>"""

        for sport, g in GOALS.items():
            km_goal  = g["km"]
            annee    = g["annee"]
            df_s     = df[(df["sport"] == sport) & (df["annee"] == annee)]
            km_done  = round(df_s["distance_km"].sum(), 1)
            pct      = round(km_done / km_goal * 100, 1)
            target   = round(km_goal / days_total * day_of_yr, 1)
            delta    = round(km_done - target, 1)
            km_left  = round(km_goal - km_done, 1)
            rate_req = round(km_left / days_left, 2) if days_left > 0 else 0

            # Rythme 30j
            since30  = today - timedelta(days=30)
            km30     = df_s[df_s["date"] >= since30]["distance_km"].sum()
            rate30   = round(km30 / 30, 2)
            proj30   = round(km_done + rate30 * days_left, 0)

            bar_color  = "#27AE60" if delta >= 0 else "#E74C3C"
            delta_txt  = f"+{delta} km d'avance ✅" if delta >= 0 else f"{delta} km de retard ⚠️"
            proj_color = "#27AE60" if proj30 >= km_goal else "#E74C3C"
            proj_txt   = f"✅ Goal atteint ({int(proj30)} km)" if proj30 >= km_goal else f"⚠️ Projection : {int(proj30)} km (manque {int(km_goal-proj30)} km)"

            bar_pct = min(pct, 100)
            html += f"""
          <div style="background:white;border-radius:8px;padding:16px;margin-bottom:12px;border-left:4px solid #FC4C02">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <b>{sport}</b>
              <span style="color:{bar_color};font-size:.85rem;font-weight:600">{delta_txt}</span>
            </div>
            <div style="background:#f0f0f0;border-radius:6px;height:10px;margin-bottom:8px">
              <div style="width:{bar_pct}%;background:{bar_color};height:10px;border-radius:6px"></div>
            </div>
            <div style="font-size:.82rem;color:#666;display:flex;gap:16px;flex-wrap:wrap">
              <span><b style="color:#333">{km_done} / {km_goal} km</b> ({pct}%)</span>
              <span>Requis : <b>{rate_req} km/j</b></span>
              <span>Ton rythme 30j : <b>{rate30} km/j</b></span>
            </div>
            <div style="margin-top:6px;font-size:.82rem;color:{proj_color}">{proj_txt}</div>
          </div>"""

        html += "</div>"
        return html
    except Exception as e:
        return f'<p style="color:#aaa;font-size:.8rem">Goals non disponibles : {e}</p>'

def send_email(new_activities):
    if not GMAIL_APPPASS or GMAIL_APPPASS == "COLLER_ICI_MOT_DE_PASSE_APP":
        log("⚠️  Email non configuré (mot de passe manquant).")
        return

    count = len(new_activities)
    subject = f"🏃 Strava Sync — {count} nouvelle{'s' if count > 1 else ''} activité{'s' if count > 1 else ''}"

    rows_html = ""
    for a in new_activities:
        r = activity_to_row(a)
        dist = f"{r['distance_km']} km" if r["distance_km"] > 0 else "—"
        duree = format_duration(r["duree_min"])
        fc = f"{r['fc_moy']} bpm" if r["fc_moy"] else "—"
        rows_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee">{r['date'][:10]}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">{r['sport']}</td>
          <td style="padding:8px;border-bottom:1px solid #eee"><b>{r['nom']}</b></td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">{dist}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">{duree}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">{fc}</td>
        </tr>"""

    goals_html = build_goals_html_email()

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:auto">
      <div style="background:#FC4C02;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">🏃 Strava Sync</h2>
        <p style="color:rgba(255,255,255,0.85);margin:4px 0 0">{count} nouvelle{'s' if count > 1 else ''} activité{'s' if count > 1 else ''} détectée{'s' if count > 1 else ''}</p>
      </div>
      <div style="background:#f9f9f9;padding:20px;border-radius:0 0 8px 8px">
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:6px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
          <thead>
            <tr style="background:#FC4C02;color:white">
              <th style="padding:10px;text-align:left">Date</th>
              <th style="padding:10px;text-align:left">Sport</th>
              <th style="padding:10px;text-align:left">Nom</th>
              <th style="padding:10px;text-align:right">Distance</th>
              <th style="padding:10px;text-align:right">Durée</th>
              <th style="padding:10px;text-align:right">FC moy.</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        {goals_html}
        <p style="color:#999;font-size:12px;margin-top:16px;text-align:center">
          Synchronisé le {datetime.now().strftime("%d/%m/%Y à %H:%M")} · Strava Agent
        </p>
      </div>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_DEST
    msg.attach(MIMEText(html, "html"))

    # Joindre les graphiques mis à jour
    for fname in ["02_km_par_mois.png", "03_progression_annuelle.png"]:
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as img_file:
                img = MIMEImage(img_file.read(), name=fname)
                msg.attach(img)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APPPASS)
            smtp.sendmail(GMAIL_USER, EMAIL_DEST, msg.as_string())
        log(f"📧 Email envoyé à {EMAIL_DEST}")
    except Exception as e:
        log(f"❌ Erreur envoi email : {e}")

def send_daily_summary():
    """Envoie un résumé journalier après 20h si aucun email n'a été envoyé aujourd'hui."""
    if not GMAIL_APPPASS or GMAIL_APPPASS == "COLLER_ICI_MOT_DE_PASSE_APP":
        return

    goals_html = build_goals_html_email()
    today_str  = datetime.now().strftime("%A %d %B %Y").capitalize()

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:auto">
      <div style="background:#555;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">📋 Résumé journalier Strava</h2>
        <p style="color:rgba(255,255,255,0.75);margin:4px 0 0">{today_str}</p>
      </div>
      <div style="background:#f9f9f9;padding:20px;border-radius:0 0 8px 8px">
        <p style="color:#888;font-style:italic;margin-bottom:16px">
          😴 Aucune nouvelle activité synchronisée aujourd'hui — le système fonctionne normalement.
        </p>
        {goals_html}
        <p style="color:#999;font-size:12px;margin-top:16px;text-align:center">
          Résumé automatique · Strava Agent
        </p>
      </div>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📋 Strava — Résumé du {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_DEST
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APPPASS)
            smtp.sendmail(GMAIL_USER, EMAIL_DEST, msg.as_string())
        log("📧 Résumé journalier envoyé.")
    except Exception as e:
        log(f"❌ Erreur résumé journalier : {e}")

# ── Main ───────────────────────────────────────────────
if __name__ == "__main__":
    log("═" * 50)

    full_sync = "--full" in sys.argv
    if full_sync:
        log("🔄 SYNC COMPLÈTE depuis 2018")
    else:
        log("🚀 Démarrage sync Strava")

    token = get_access_token()
    existing_ids = load_existing_ids()

    if full_sync:
        # Depuis le 1er janvier 2018
        import calendar
        after = calendar.timegm((2018, 1, 1, 0, 0, 0))
        log(f"🕐 Récupération depuis le 01/01/2018...")
    else:
        # Utiliser le timestamp du dernier sync (avec 2h de chevauchement pour éviter les oublis)
        after = get_last_sync_timestamp() - (2 * 3600)
        log(f"🕐 Recherche des activités depuis : {datetime.fromtimestamp(after).strftime('%d/%m/%Y %H:%M')}")

    recent = fetch_recent_activities(token, after)

    # Double vérification par ID pour éviter les doublons
    new_ones = [a for a in recent if str(a.get("id")) not in existing_ids]

    email_sent = False

    if not new_ones:
        log("✅ Aucune nouvelle activité.")
    else:
        log(f"🆕 {len(new_ones)} nouvelle(s) activité(s) trouvée(s) !")
        append_to_csv(new_ones)
        regenerate_graphs()
        regenerate_dashboard()
        send_email(new_ones)
        email_sent = True

    # Résumé journalier après 20h si pas d'email envoyé aujourd'hui
    if not email_sent and should_send_daily_summary():
        log("🌙 Envoi du résumé journalier...")
        send_daily_summary()
        email_sent = True

    save_last_sync_timestamp(email_sent_today=email_sent)
    log("✅ Sync terminée.")
