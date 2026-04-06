"""
Strava Analyse - Script autonome
Récupère tes activités Strava et génère des graphiques d'analyse.

Prérequis :
  pip install requests matplotlib pandas

Usage :
  python strava_analyse.py
"""

import http.server
import urllib.parse
import webbrowser
import requests
import json
import threading
import os
import time
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
CLIENT_ID     = "212809"
CLIENT_SECRET = "ac7d4e9a7a33e4ced25c3ed01fcf90e435ebec26"
REDIRECT_URI  = "http://localhost:8765"
TOKEN_FILE    = "strava_token.json"
OUTPUT_DIR    = "strava_output"

# ── OAuth ──────────────────────────────────────────────────────────────────────
auth_code = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>✅ Authentification réussie ! Tu peux fermer cet onglet.</h2>".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
    def log_message(self, *args):
        pass

def authenticate():
    """Lance le flux OAuth et retourne un access token."""
    global auth_code
    auth_code = None

    server = http.server.HTTPServer(("localhost", 8765), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.daemon = True
    thread.start()

    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}&response_type=code"
        f"&redirect_uri={REDIRECT_URI}&approval_prompt=force"
        f"&scope=read,activity:read_all"
    )
    print("🌐 Ouverture du navigateur pour l'authentification Strava...")
    webbrowser.open(auth_url)

    print("⏳ En attente de l'autorisation...")
    thread.join(timeout=120)
    server.server_close()

    if not auth_code:
        raise Exception("❌ Aucun code reçu. Relance le script et autorise l'accès.")

    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code"
    })
    token = resp.json()
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f)
    athlete = token.get("athlete", {})
    print(f"✅ Connecté : {athlete.get('firstname', '')} {athlete.get('lastname', '')}")
    return token["access_token"]

def get_access_token():
    """Retourne un token valide (refresh si nécessaire)."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = json.load(f)
        if token.get("expires_at", 0) > time.time() + 60:
            return token["access_token"]
        # Refresh
        resp = requests.post("https://www.strava.com/oauth/token", data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"]
        })
        new_token = resp.json()
        with open(TOKEN_FILE, "w") as f:
            json.dump(new_token, f)
        return new_token["access_token"]
    return authenticate()

# ── Récupération des activités ─────────────────────────────────────────────────
def fetch_all_activities(token):
    """Récupère toutes les activités depuis l'API Strava."""
    activities = []
    page = 1
    print("📥 Récupération des activités...", end="", flush=True)
    while True:
        resp = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 200, "page": page}
        )
        batch = resp.json()
        if not batch or not isinstance(batch, list):
            break
        activities.extend(batch)
        print(f" {len(activities)}", end="", flush=True)
        if len(batch) < 200:
            break
        page += 1
    print(f"\n✅ {len(activities)} activités récupérées.")
    return activities

# ── Nettoyage des données ──────────────────────────────────────────────────────
SPORT_LABELS = {
    "Run": "Course", "Ride": "Vélo", "Swim": "Natation",
    "Walk": "Marche", "Hike": "Randonnée", "VirtualRide": "Vélo virtuel",
    "VirtualRun": "Course virtuelle", "WeightTraining": "Musculation",
    "Workout": "Entraînement", "Yoga": "Yoga",
}

def build_dataframe(activities):
    rows = []
    for a in activities:
        sport = a.get("type", "Autre")
        rows.append({
            "date":          pd.to_datetime(a["start_date_local"]),
            "sport":         SPORT_LABELS.get(sport, sport),
            "nom":           a.get("name", ""),
            "distance_km":   round(a.get("distance", 0) / 1000, 2),
            "duree_min":     round(a.get("moving_time", 0) / 60, 1),
            "denivele_m":    round(a.get("total_elevation_gain", 0), 0),
            "vitesse_moy":   round(a.get("average_speed", 0) * 3.6, 2),
            "fc_moy":        a.get("average_heartrate"),
            "calories":      a.get("kilojoules"),
        })
    df = pd.DataFrame(rows).sort_values("date")
    df["annee"]     = df["date"].dt.year
    df["mois"]      = df["date"].dt.to_period("M")
    df["semaine"]   = df["date"].dt.to_period("W")
    return df

# ── Graphiques ─────────────────────────────────────────────────────────────────
COULEURS = ["#FC4C02", "#4A90D9", "#27AE60", "#F39C12", "#9B59B6", "#E74C3C"]

def save_fig(fig, name):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  💾 {path}")

def graph_repartition_sports(df):
    counts = df["sport"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        counts.values, labels=counts.index, autopct="%1.1f%%",
        colors=COULEURS[:len(counts)], startangle=90
    )
    ax.set_title("Répartition des activités par sport", fontsize=14, fontweight="bold")
    save_fig(fig, "01_repartition_sports.png")

def graph_km_par_mois(df):
    sports = ["Course", "Vélo"]
    df_sport = df[df["sport"].isin(sports)]
    if df_sport.empty:
        return
    pivot = df_sport.groupby(["mois", "sport"])["distance_km"].sum().unstack(fill_value=0)
    pivot.index = pivot.index.to_timestamp()

    fig, ax = plt.subplots(figsize=(14, 5))
    bottom = None
    for i, col in enumerate(pivot.columns):
        ax.bar(pivot.index, pivot[col], label=col,
               color=COULEURS[i], bottom=bottom, width=20)
        bottom = pivot[col] if bottom is None else bottom + pivot[col]
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45, ha="right")
    ax.set_ylabel("Distance (km)")
    ax.set_title("Distance mensuelle par sport", fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    save_fig(fig, "02_km_par_mois.png")

def graph_progression_annuelle(df):
    df_run = df[df["sport"] == "Course"].copy()
    if df_run.empty:
        return
    yearly = df_run.groupby("annee")["distance_km"].sum()
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(yearly.index.astype(str), yearly.values, color="#FC4C02")
    for bar, val in zip(bars, yearly.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                f"{val:.0f} km", ha="center", fontsize=10, fontweight="bold")
    ax.set_ylabel("Distance totale (km)")
    ax.set_title("Progression annuelle — Course à pied", fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    save_fig(fig, "03_progression_annuelle.png")

def graph_frequence_cardiaque(df):
    df_fc = df[df["fc_moy"].notna() & (df["sport"] == "Course")].copy()
    if df_fc.empty:
        return
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.scatter(df_fc["date"], df_fc["fc_moy"], alpha=0.5, color="#E74C3C", s=20)
    # Moyenne mobile 30 jours
    df_fc = df_fc.set_index("date").sort_index()
    rolling = df_fc["fc_moy"].rolling("30D").mean()
    ax.plot(rolling.index, rolling.values, color="#C0392B", linewidth=2, label="Moyenne 30j")
    ax.set_ylabel("FC moyenne (bpm)")
    ax.set_title("Fréquence cardiaque moyenne — Course à pied", fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(alpha=0.3)
    save_fig(fig, "04_frequence_cardiaque.png")

def graph_heatmap_semaine(df):
    df_run = df[df["sport"] == "Course"].copy()
    if df_run.empty:
        return
    df_run["jour_semaine"] = df_run["date"].dt.dayofweek
    df_run["heure"]        = df_run["date"].dt.hour
    pivot = df_run.groupby(["heure", "jour_semaine"]).size().unstack(fill_value=0)
    pivot = pivot.reindex(columns=range(7), fill_value=0)
    jours = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    fig, ax = plt.subplots(figsize=(10, 7))
    im = ax.imshow(pivot.values, aspect="auto", cmap="Oranges")
    ax.set_xticks(range(7)); ax.set_xticklabels(jours)
    ax.set_yticks(range(0, 24, 2)); ax.set_yticklabels([f"{h}h" for h in range(0, 24, 2)])
    ax.set_title("Heatmap des sorties — Heure × Jour de la semaine", fontsize=14, fontweight="bold")
    plt.colorbar(im, ax=ax, label="Nombre d'activités")
    save_fig(fig, "05_heatmap_sorties.png")

# ── Export CSV ─────────────────────────────────────────────────────────────────
def export_csv(df):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "activites.csv")
    df.drop(columns=["mois", "semaine", "annee"], errors="ignore").to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  💾 {path}")

# ── Stats résumé ───────────────────────────────────────────────────────────────
def print_stats(df):
    print("\n" + "═"*50)
    print("  📊 RÉSUMÉ DE TES ACTIVITÉS")
    print("═"*50)
    print(f"  Activités totales  : {len(df)}")
    print(f"  Période            : {df['date'].min().strftime('%d/%m/%Y')} → {df['date'].max().strftime('%d/%m/%Y')}")
    print(f"  Distance totale    : {df['distance_km'].sum():,.0f} km")
    print(f"  Temps total        : {df['duree_min'].sum()/60:,.0f} heures")
    print()
    by_sport = df.groupby("sport").agg(
        activites=("distance_km", "count"),
        distance=("distance_km", "sum"),
        duree_h=("duree_min", lambda x: round(x.sum()/60, 0))
    ).sort_values("activites", ascending=False)
    print(by_sport.to_string())
    print("═"*50)

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🚴 STRAVA ANALYSE\n")
    token      = get_access_token()
    activities = fetch_all_activities(token)
    df         = build_dataframe(activities)

    print_stats(df)

    print("\n📈 Génération des graphiques...")
    graph_repartition_sports(df)
    graph_km_par_mois(df)
    graph_progression_annuelle(df)
    graph_frequence_cardiaque(df)
    graph_heatmap_semaine(df)
    export_csv(df)

    print(f"\n✅ Tout est prêt dans le dossier '{OUTPUT_DIR}/' !")
