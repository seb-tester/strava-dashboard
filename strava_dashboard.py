"""
Strava Dashboard v4 — Fenêtre dynamique 5 ans + Historique complet
"""

import pandas as pd
import json
import os
from datetime import datetime, timedelta, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE   = os.path.join(SCRIPT_DIR, "strava_output", "activites.csv")
OUT_FILE   = os.path.join(SCRIPT_DIR, "strava_output", "dashboard.html")

MOIS_FR = ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Août","Sep","Oct","Nov","Déc"]
MOIS_LONG = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
COULEURS_ANNEES = ["#FC4C02","#4A90D9","#27AE60","#F39C12","#9B59B6","#1ABC9C","#E74C3C"]
SPORTS_PRIORITAIRES = ["Course","Vélo","Natation","Randonnée","Marche","Vélo virtuel","Course virtuelle"]

# ════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════
CURRENT_YEAR = datetime.now().year
WINDOW_YEARS = 5   # Nombre d'années à afficher dans les graphiques comparatifs
MIN_YEAR     = CURRENT_YEAR - WINDOW_YEARS + 1

GOALS = {
    "Vélo":   {"km": 2050},   # Goal pour l'année en cours (CURRENT_YEAR)
    "Course": {"km": 560},
}
MIN_DIST = {"Course": 5, "Vélo": 20, "default": 1}
# ════════════════════════════════════════════════

def load_data():
    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig", on_bad_lines="skip")
    df["date"]        = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
    df["annee"]       = df["date"].dt.year
    df["mois_num"]    = df["date"].dt.month
    df["jour_annee"]  = df["date"].dt.dayofyear
    df["distance_km"] = pd.to_numeric(df["distance_km"], errors="coerce").fillna(0)
    df["duree_min"]   = pd.to_numeric(df["duree_min"],   errors="coerce").fillna(0)
    df["fc_moy"]      = pd.to_numeric(df["fc_moy"],      errors="coerce")
    df["vitesse_moy"] = pd.to_numeric(df["vitesse_moy"], errors="coerce")
    return df

def window(df):
    """Retourne le df filtré sur les WINDOW_YEARS dernières années (dynamique)."""
    return df[df["annee"] >= MIN_YEAR].copy()

def top_sports(df, n=4):
    counts = df["sport"].value_counts()
    ordered = [s for s in SPORTS_PRIORITAIRES if s in counts.index]
    others  = [s for s in counts.index if s not in ordered]
    return (ordered + others)[:n]

# ── Goals (année courante, dynamique) ──────────
def build_goals(df):
    today      = datetime.now()
    day_of_yr  = today.timetuple().tm_yday
    days_total = 366 if CURRENT_YEAR % 4 == 0 else 365
    days_left  = days_total - day_of_yr

    results = []
    for sport, g in GOALS.items():
        km_goal  = g["km"]
        df_sport = df[(df["sport"] == sport) & (df["annee"] == CURRENT_YEAR)]
        km_done  = round(df_sport["distance_km"].sum(), 1)
        pct      = round(km_done / km_goal * 100, 1)

        km_target_today = round(km_goal / days_total * day_of_yr, 1)
        delta           = round(km_done - km_target_today, 1)
        delta_days      = round(delta / (km_goal / days_total), 1) if km_goal > 0 else 0

        def projection(days_window):
            since = today - timedelta(days=days_window)
            km_w  = df_sport[df_sport["date"] >= since]["distance_km"].sum()
            rate  = km_w / days_window
            proj  = round(km_done + rate * days_left, 0)
            return {"km": proj, "rate": round(rate, 2), "window": days_window}

        proj30 = projection(30)
        proj90 = projection(90)
        km_remaining  = km_goal - km_done
        rate_required = round(km_remaining / days_left, 2) if days_left > 0 else 0
        rate_ideal    = round(km_goal / days_total, 2)

        if delta >= 0:
            tag = {"label": f"+{delta} km d'avance ({delta_days:.0f} j)", "couleur": "#27AE60", "icone": "✅"}
        else:
            tag = {"label": f"{delta} km de retard ({abs(delta_days):.0f} j)", "couleur": "#E74C3C", "icone": "⚠️"}

        results.append({
            "sport": sport, "km_goal": km_goal, "km_done": km_done,
            "km_remaining": round(km_remaining, 1), "pct": pct,
            "km_target_today": km_target_today, "delta": delta,
            "rate_required": rate_required, "rate_ideal": rate_ideal,
            "proj30": proj30, "proj90": proj90, "tag": tag,
            "annee": CURRENT_YEAR,
        })
    return results

# ── Personal Bests (all-time, sur df complet) ──
def fmt_pace(km_per_h):
    if not km_per_h or km_per_h == 0: return "—"
    sec_per_km = 3600 / km_per_h
    m = int(sec_per_km // 60); s = int(sec_per_km % 60)
    return f"{m}:{s:02d} /km"

def fmt_duration(minutes):
    h = int(minutes // 60); m = int(minutes % 60)
    return f"{h}h{m:02d}" if h else f"{m} min"

def build_personal_bests(df):
    sport_configs = {
        "Course": {"min_km": MIN_DIST["Course"], "metrics": [
            {"key": "distance_km", "label": "Plus longue distance", "fmt": lambda v: f"{v:.1f} km"},
            {"key": "duree_min",   "label": "Plus longue durée",    "fmt": lambda v: fmt_duration(v)},
            {"key": "vitesse_moy", "label": "Meilleur rythme",      "fmt": lambda v: fmt_pace(v)},
        ]},
        "Vélo": {"min_km": MIN_DIST["Vélo"], "metrics": [
            {"key": "distance_km", "label": "Plus longue sortie",  "fmt": lambda v: f"{v:.1f} km"},
            {"key": "duree_min",   "label": "Plus longue durée",   "fmt": lambda v: fmt_duration(v)},
            {"key": "vitesse_moy", "label": "Meilleure vitesse",   "fmt": lambda v: f"{v:.1f} km/h"},
        ]}
    }
    records = {}
    for sport, cfg in sport_configs.items():
        dfs = df[(df["sport"] == sport) & (df["distance_km"] >= cfg["min_km"])].copy()
        if dfs.empty: continue
        annees = sorted(dfs["annee"].unique().tolist())
        sport_records = {"sport": sport, "metrics": []}
        for metric in cfg["metrics"]:
            key = metric["key"]
            dff = dfs[dfs[key].notna() & (dfs[key] > 0)].copy()
            if dff.empty: continue
            cols = list(dict.fromkeys(["date","nom","distance_km","duree_min","vitesse_moy",key]))
            top3 = dff.nlargest(3, key)[cols]
            podium = []
            for _, row in top3.iterrows():
                podium.append({
                    "value":    metric["fmt"](row[key]),
                    "raw":      round(row[key], 2),
                    "date":     row["date"].strftime("%d %b %Y"),
                    "nom":      str(row["nom"])[:40],
                    "distance": f"{row['distance_km']:.1f} km",
                    "duree":    fmt_duration(row["duree_min"]),
                })
            year_bests = {}
            for annee in annees:
                dfy = dff[dff["annee"] == annee]
                if dfy.empty:
                    year_bests[str(annee)] = {"value": "—", "raw": None}
                else:
                    best = dfy.loc[dfy[key].idxmax()]
                    year_bests[str(annee)] = {
                        "value": metric["fmt"](best[key]),
                        "raw":   round(best[key], 2),
                        "date":  best["date"].strftime("%d %b"),
                        "nom":   str(best["nom"])[:30],
                    }
            sport_records["metrics"].append({
                "label": metric["label"], "key": key,
                "podium": podium, "year_bests": year_bests,
                "annees": [str(a) for a in annees],
            })
        records[sport] = sport_records
    return records

# ── Historique complet (pour onglet filtrable) ─
def build_history(df):
    """Retourne toutes les activités triées par date desc pour l'onglet historique."""
    df_sorted = df.sort_values("date", ascending=False).copy()
    rows = []
    for _, r in df_sorted.iterrows():
        fc = round(r["fc_moy"], 1) if pd.notna(r["fc_moy"]) else None
        vit = round(r["vitesse_moy"], 1) if pd.notna(r["vitesse_moy"]) else None
        rows.append({
            "date":    r["date"].strftime("%Y-%m-%d"),
            "sport":   str(r["sport"]),
            "nom":     str(r["nom"]),
            "km":      round(r["distance_km"], 2),
            "duree":   fmt_duration(r["duree_min"]),
            "duree_m": round(r["duree_min"], 1),
            "fc":      fc,
            "vit":     vit,
            "annee":   int(r["annee"]),
            "mois":    int(r["mois_num"]),
        })
    sports = sorted(df["sport"].unique().tolist())
    annees = sorted(df["annee"].unique().tolist(), reverse=True)
    return {"rows": rows, "sports": sports, "annees": [int(a) for a in annees]}

# ── Sport data (fenêtre 5 ans) ─────────────────
def compute_trend(df, sport=None):
    now    = df["date"].max()
    d90    = now - timedelta(days=90)
    d90_1y = d90 - timedelta(days=365)
    now_1y = now - timedelta(days=365)
    dff = df if sport is None else df[df["sport"] == sport]
    recent = dff[dff["date"] >= d90]["distance_km"].sum()
    prev   = dff[(dff["date"] >= d90_1y) & (dff["date"] < now_1y)]["distance_km"].sum()
    if prev == 0:
        return {"label": "Nouveau", "pct": None, "couleur": "#888", "icone": "✦"}
    pct = round((recent - prev) / prev * 100, 1)
    if pct >= 10:   return {"label": f"+{pct}% vs an dernier", "pct": pct, "couleur": "#27AE60", "icone": "↗"}
    elif pct <= -10: return {"label": f"{pct}% vs an dernier", "pct": pct, "couleur": "#E74C3C", "icone": "↘"}
    else:            return {"label": f"{pct:+}% vs an dernier", "pct": pct, "couleur": "#F39C12", "icone": "→"}

def compute_cardio_trend(df, sport):
    now    = df["date"].max()
    d90    = now - timedelta(days=90)
    d90_1y = d90 - timedelta(days=365)
    now_1y = now - timedelta(days=365)
    dff = df[(df["sport"] == sport) & df["fc_moy"].notna()]
    fc_r = dff[dff["date"] >= d90]["fc_moy"].mean()
    fc_p = dff[(dff["date"] >= d90_1y) & (dff["date"] < now_1y)]["fc_moy"].mean()
    if pd.isna(fc_r) or pd.isna(fc_p) or fc_p == 0: return None
    diff = round(fc_r - fc_p, 1)
    if diff <= -3:   return {"label": f"FC {diff:+} bpm (cardio ↗)", "couleur": "#27AE60", "icone": "↗"}
    elif diff >= 3:  return {"label": f"FC {diff:+} bpm (cardio ↘)", "couleur": "#E74C3C", "icone": "↘"}
    else:            return {"label": f"FC {diff:+} bpm (stable)", "couleur": "#F39C12", "icone": "→"}

def build_sport_data(df_win, df_full, sport):
    """Graphiques comparatifs sur la fenêtre 5 ans."""
    annees = sorted(df_win[df_win["sport"] == sport]["annee"].unique().tolist())
    dfs = df_win[df_win["sport"] == sport]
    dist_datasets = []
    for i, annee in enumerate(annees):
        df_a = dfs[dfs["annee"] == annee]
        vals = [round(df_a[df_a["mois_num"] == m]["distance_km"].sum(), 1) for m in range(1, 13)]
        dist_datasets.append({"label": str(annee), "data": vals,
            "backgroundColor": COULEURS_ANNEES[i % len(COULEURS_ANNEES)], "borderRadius": 4})
    cardio_datasets = []
    has_cardio = dfs["fc_moy"].notna().sum() > 0
    if has_cardio:
        for i, annee in enumerate(annees):
            df_a = dfs[dfs["annee"] == annee]
            vals = []
            for m in range(1, 13):
                fc = df_a[df_a["mois_num"] == m]["fc_moy"].mean()
                vals.append(round(fc, 1) if not pd.isna(fc) else None)
            cardio_datasets.append({"label": str(annee), "data": vals,
                "borderColor": COULEURS_ANNEES[i % len(COULEURS_ANNEES)],
                "backgroundColor": "transparent", "borderWidth": 2.5, "pointRadius": 4, "tension": 0.3})
    return {
        "sport": sport, "annees": [str(a) for a in annees],
        "dist_datasets": dist_datasets, "cardio_datasets": cardio_datasets,
        "has_cardio": has_cardio,
        "trend_dist":   compute_trend(df_full, sport),
        "trend_cardio": compute_cardio_trend(df_full, sport) if has_cardio else None,
        "window_label": f"{MIN_YEAR}–{CURRENT_YEAR}",
    }

def _cumul_datasets(df_sub, annees):
    """Calcule les datasets de progression cumulée pour un sous-ensemble de df."""
    import datetime as dt
    labels = list(range(1, 367))
    label_dates = []
    for j in labels:
        try:
            d = dt.date(2024, 1, 1) + dt.timedelta(days=j-1)
            label_dates.append(d.strftime("%d %b"))
        except: label_dates.append(str(j))
    datasets = []
    for i, annee in enumerate(annees):
        df_a = df_sub[df_sub["annee"] == annee].sort_values("date")
        cum = {}; total = 0
        for _, row in df_a.iterrows():
            total += row["distance_km"]
            cum[int(row["jour_annee"])] = round(total, 1)
        data = []; last = 0
        max_jour = 366 if annee == CURRENT_YEAR else 365
        for j in labels:
            if j in cum: last = cum[j]
            data.append(last if j <= max_jour else None)
        datasets.append({"label": str(annee), "data": data,
            "borderColor": COULEURS_ANNEES[i % len(COULEURS_ANNEES)],
            "backgroundColor": "transparent", "borderWidth": 2.5, "pointRadius": 0, "tension": 0.3})
    return {"labels": label_dates, "datasets": datasets}

def build_cumulative(df_win, sports):
    """Retourne le cumulatif total + un cumulatif par sport."""
    annees = sorted(df_win["annee"].unique().tolist())
    result = {"total": _cumul_datasets(df_win, annees), "by_sport": {}}
    for sport in sports:
        dfs = df_win[df_win["sport"] == sport]
        ann_s = sorted(dfs["annee"].unique().tolist())
        if ann_s:
            result["by_sport"][sport] = _cumul_datasets(dfs, ann_s)
    return result

def _table_data(df_sub, annees):
    """Calcule le tableau comparatif mensuel pour un sous-ensemble."""
    rows = []
    for m in range(1, 13):
        row = {"mois": MOIS_FR[m-1]}
        for annee in annees:
            df_am = df_sub[(df_sub["annee"] == annee) & (df_sub["mois_num"] == m)]
            row[str(annee)] = {"km": round(df_am["distance_km"].sum(), 0), "count": len(df_am)}
        rows.append(row)
    total_row = {"mois": "TOTAL"}
    for annee in annees:
        df_a = df_sub[df_sub["annee"] == annee]
        total_row[str(annee)] = {"km": round(df_a["distance_km"].sum(), 0), "count": len(df_a)}
    rows.append(total_row)
    return {"annees": [str(a) for a in annees], "rows": rows}

def build_table(df_win, sports):
    """Retourne le tableau total + un tableau par sport."""
    annees = sorted(df_win["annee"].unique().tolist())
    result = {"total": _table_data(df_win, annees), "by_sport": {}}
    for sport in sports:
        dfs = df_win[df_win["sport"] == sport]
        ann_s = sorted(dfs["annee"].unique().tolist())
        if ann_s:
            result["by_sport"][sport] = _table_data(dfs, ann_s)
    return result

def build_stats(df_win, df_full):
    annees = sorted(df_win["annee"].unique().tolist(), reverse=True)
    stats = [{"annee": str(a),
              "km": round(df_win[df_win["annee"]==a]["distance_km"].sum(), 0),
              "activites": len(df_win[df_win["annee"]==a]),
              "heures": round(df_win[df_win["annee"]==a]["duree_min"].sum()/60, 0)}
             for a in annees]
    return {"stats": stats, "global_trend": compute_trend(df_full)}

# ── Génération HTML ────────────────────────────
def generate_html(data):
    now = datetime.now().strftime("%d/%m/%Y à %H:%M")

    # ── Sport tabs ─────────────────────────────
    sports_tabs = ""
    sports_panels = ""
    for idx, sd in enumerate(data["sports_data"]):
        sport  = sd["sport"]
        active = "active" if idx == 0 else ""
        sports_tabs += f'<button class="{active}" onclick="showSportTab(\'{sport}\',this)">{sport}</button>\n'
        td = sd["trend_dist"]; tc = sd.get("trend_cardio")
        tag_dist   = f'<span class="tag" style="background:{td["couleur"]}20;color:{td["couleur"]};border:1px solid {td["couleur"]}40">{td["icone"]} {td["label"]}</span>'
        tag_cardio = f'<span class="tag" style="background:{tc["couleur"]}20;color:{tc["couleur"]};border:1px solid {tc["couleur"]}40">❤️ {tc["label"]}</span>' if tc else ""
        tag_window = f'<span class="tag" style="background:#f0f0f0;color:#888;border:1px solid #ddd">📅 {sd["window_label"]}</span>'
        cardio_section = ""
        if sd["has_cardio"]:
            cardio_section = f"""<div class="card" style="margin-top:18px">
              <div class="card-header"><h2>❤️ FC moyenne — {sport}</h2><div class="tags">{tag_cardio}</div></div>
              <p class="hint">FC qui baisse à même effort = cardio qui s'améliore 💪</p>
              <canvas id="cardio_{idx}" height="80"></canvas></div>"""
        sports_panels += f"""<div id="sport_{sport.replace(' ','_')}" class="sport-panel {'active' if idx==0 else ''}">
          <div class="card"><div class="card-header"><h2>📏 Distance mensuelle — {sport}</h2><div class="tags">{tag_dist}{tag_window}</div></div>
          <canvas id="dist_{idx}" height="90"></canvas></div>{cardio_section}</div>\n"""

    # ── Goals HTML ─────────────────────────────
    goals_html = ""
    for g in data["goals"]:
        sport = g["sport"]; pct = min(g["pct"], 100)
        tag = g["tag"]; bar_color = "#27AE60" if g["delta"] >= 0 else "#E74C3C"
        proj30 = g["proj30"]; proj90 = g["proj90"]
        p30_color = "#27AE60" if proj30["km"] >= g["km_goal"] else "#E74C3C"
        p90_color = "#27AE60" if proj90["km"] >= g["km_goal"] else "#E74C3C"
        goals_html += f"""<div class="card goal-card">
          <div class="card-header">
            <h2>🎯 {sport} {g["annee"]} — {g["km_goal"]} km</h2>
            <span class="tag" style="background:{tag['couleur']}20;color:{tag['couleur']};border:1px solid {tag['couleur']}40">{tag['icone']} {tag['label']}</span>
          </div>
          <div class="progress-row">
            <span class="prog-label">{g["km_done"]} km</span>
            <div class="progress-bar-wrap">
              <div class="progress-bar" style="width:{pct}%;background:{bar_color}"></div>
              <div class="progress-ideal" style="left:{min(round(g['km_target_today']/g['km_goal']*100,1),100)}%"></div>
            </div>
            <span class="prog-label">{g["km_goal"]} km</span>
          </div>
          <div class="prog-pct">{g["pct"]}% complété</div>
          <div class="goal-stats">
            <div class="gstat"><div class="gval">{g["rate_required"]} km/j</div><div class="glbl">Rythme requis</div></div>
            <div class="gstat"><div class="gval">{proj30["rate"]} km/j</div><div class="glbl">Ton rythme (30j)</div></div>
            <div class="gstat"><div class="gval">{g["km_remaining"]} km</div><div class="glbl">Restants</div></div>
          </div>
          <div class="projections">
            <div class="proj-item">
              <span class="proj-label">📊 Projection 30j :</span>
              <span class="proj-val" style="color:{p30_color};font-weight:700">{int(proj30['km'])} km</span>
              <span class="proj-rate">({proj30['rate']} km/j)</span>
              {"<span class='proj-ok'>✅ Goal atteint</span>" if proj30['km'] >= g['km_goal'] else f"<span class='proj-miss'>⚠️ Manque {int(g['km_goal']-proj30['km'])} km</span>"}
            </div>
            <div class="proj-item">
              <span class="proj-label">📊 Projection 90j :</span>
              <span class="proj-val" style="color:{p90_color};font-weight:700">{int(proj90['km'])} km</span>
              <span class="proj-rate">({proj90['rate']} km/j)</span>
              {"<span class='proj-ok'>✅ Goal atteint</span>" if proj90['km'] >= g['km_goal'] else f"<span class='proj-miss'>⚠️ Manque {int(g['km_goal']-proj90['km'])} km</span>"}
            </div>
          </div>
        </div>"""

    # ── Records HTML ───────────────────────────
    medals = ["🥇","🥈","🥉"]
    records_html = ""
    for sport, rec in data["records"].items():
        records_html += f'<h3 style="margin:24px 0 12px;color:#FC4C02">{sport}</h3>'
        for metric in rec["metrics"]:
            annees = metric["annees"]
            podium_html = ""
            for i, p in enumerate(metric["podium"]):
                size = ["1.3rem","1.1rem","1rem"][i]
                podium_html += f"""<div class="podium-item">
                  <div style="font-size:{size}">{medals[i]}</div>
                  <div class="pod-val">{p['value']}</div>
                  <div class="pod-meta">{p['nom']}</div>
                  <div class="pod-date">{p['date']} · {p['distance']}</div>
                </div>"""
            # En-têtes années seulement (sans évolution)
            yr_headers = ""
            for a in annees:
                yr_headers += f"<th>{a}</th>"

            row_cells = ""
            for a in annees:
                yb = metric["year_bests"].get(a, {"value":"—", "raw": None})
                row_cells += f'<td><b>{yb["value"]}</b>'
                if yb.get("date"): row_cells += f'<br><span class="cnt">{yb["date"]}</span>'
                row_cells += "</td>"

            records_html += f"""<div class="card" style="margin-bottom:16px">
              <div class="card-header"><h2>{metric['label']}</h2></div>
              <div class="podium-row">{podium_html}</div>
              <div style="margin-top:16px;overflow-x:auto">
                <table><thead><tr><th>Année</th>{yr_headers}</tr></thead>
                <tbody><tr><td>Record</td>{row_cells}</tr></tbody></table>
              </div></div>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Strava Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f2f2f2;color:#333}}
  header{{background:#FC4C02;color:white;padding:18px 32px;display:flex;align-items:center;gap:14px}}
  header h1{{font-size:1.5rem;font-weight:700}}
  header p{{font-size:.8rem;opacity:.8;margin-top:2px}}
  .stats-bar{{background:white;border-bottom:1px solid #e8e8e8;padding:14px 32px;display:flex;gap:28px;overflow-x:auto;align-items:center}}
  .stat{{text-align:center;min-width:90px}}
  .stat .val{{font-size:1.4rem;font-weight:700;color:#FC4C02}}
  .stat .lbl{{font-size:.72rem;color:#999;text-transform:uppercase;letter-spacing:.4px}}
  .stat .yr{{font-size:.68rem;color:#ccc}}
  .sep{{width:1px;min-width:1px;background:#eee;height:40px}}
  .global-tag{{margin-left:auto}}
  .tag{{display:inline-block;padding:4px 10px;border-radius:20px;font-size:.78rem;font-weight:600;white-space:nowrap}}
  nav.main-nav{{background:white;border-bottom:2px solid #eee;padding:0 32px;display:flex;flex-wrap:wrap}}
  nav.main-nav button{{padding:13px 20px;border:none;background:none;cursor:pointer;font-size:.88rem;
    color:#666;border-bottom:3px solid transparent;margin-bottom:-2px;transition:all .15s}}
  nav.main-nav button:hover{{color:#FC4C02}}
  nav.main-nav button.active{{color:#FC4C02;border-bottom-color:#FC4C02;font-weight:600}}
  nav.sport-nav{{background:#fafafa;border-bottom:1px solid #eee;padding:0 32px;display:flex;gap:4px}}
  nav.sport-nav button{{padding:9px 18px;border:none;background:none;cursor:pointer;font-size:.85rem;
    color:#888;border-radius:6px 6px 0 0;transition:all .15s}}
  nav.sport-nav button:hover{{background:#fff3ef;color:#FC4C02}}
  nav.sport-nav button.active{{background:white;color:#FC4C02;font-weight:600;box-shadow:0 -2px 0 #FC4C02 inset}}
  main{{padding:24px 32px;max-width:1200px;margin:auto}}
  .tab{{display:none}} .tab.active{{display:block}}
  .sport-panel{{display:none}} .sport-panel.active{{display:block}}
  .card{{background:white;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.07);padding:22px;margin-bottom:20px}}
  .card-header{{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}}
  .card-header h2{{font-size:.95rem;font-weight:600;color:#555;margin:0}}
  .tags{{display:flex;gap:8px;flex-wrap:wrap}}
  .hint{{font-size:.78rem;color:#aaa;margin-bottom:16px}}
  .goal-card{{border-left:4px solid #FC4C02}}
  .progress-row{{display:flex;align-items:center;gap:12px;margin:8px 0 4px}}
  .progress-bar-wrap{{flex:1;height:16px;background:#f0f0f0;border-radius:8px;position:relative;overflow:visible}}
  .progress-bar{{height:100%;border-radius:8px;transition:width .6s ease;min-width:4px}}
  .progress-ideal{{position:absolute;top:-4px;width:3px;height:24px;background:#333;border-radius:2px;transform:translateX(-50%)}}
  .prog-label{{font-size:.8rem;color:#888;white-space:nowrap;min-width:60px}}
  .prog-pct{{font-size:.8rem;color:#aaa;margin-bottom:14px}}
  .goal-stats{{display:flex;border:1px solid #f0f0f0;border-radius:8px;overflow:hidden;margin-bottom:14px}}
  .gstat{{flex:1;padding:12px;text-align:center;border-right:1px solid #f0f0f0}}
  .gstat:last-child{{border-right:none}}
  .gval{{font-size:1.2rem;font-weight:700;color:#FC4C02}}
  .glbl{{font-size:.72rem;color:#999;text-transform:uppercase;margin-top:2px}}
  .projections{{display:flex;flex-direction:column;gap:8px}}
  .proj-item{{display:flex;align-items:center;gap:10px;font-size:.85rem;flex-wrap:wrap}}
  .proj-label{{color:#888;min-width:140px}}
  .proj-val{{font-size:1rem}}
  .proj-rate{{color:#bbb}}
  .proj-ok{{color:#27AE60;font-size:.8rem}}
  .proj-miss{{color:#E74C3C;font-size:.8rem}}
  .podium-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px}}
  .podium-item{{flex:1;min-width:130px;background:#fff8f5;border-radius:8px;padding:12px;text-align:center;border:1px solid #ffe8df}}
  .pod-val{{font-size:1.1rem;font-weight:700;color:#FC4C02;margin:4px 0}}
  .pod-meta{{font-size:.78rem;color:#555;margin-bottom:2px}}
  .pod-date{{font-size:.72rem;color:#aaa}}
  table{{width:100%;border-collapse:collapse;font-size:.87rem}}
  th{{background:#FC4C02;color:white;padding:10px 12px;text-align:center;cursor:pointer;user-select:none}}
  th:first-child{{text-align:left}}
  th:hover{{background:#e04400}}
  td{{padding:9px 12px;text-align:center;border-bottom:1px solid #f0f0f0}}
  td:first-child{{text-align:left}}
  tr:hover td{{background:#fff8f5}}
  .up{{color:#27AE60}} .down{{color:#E74C3C}}
  .cnt{{color:#bbb;font-size:.78rem}}

  /* Historique */
  .hist-filters{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;align-items:flex-end}}
  .hist-filters label{{font-size:.8rem;color:#888;display:flex;flex-direction:column;gap:4px}}
  .hist-filters input,.hist-filters select{{
    padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:.88rem;
    background:white;color:#333;min-width:130px}}
  .hist-filters input:focus,.hist-filters select:focus{{outline:none;border-color:#FC4C02}}
  .search-wrap{{flex:1;min-width:200px}}
  .search-wrap input{{width:100%;padding:8px 12px 8px 36px}}
  .search-icon{{position:relative}}
  .search-icon::before{{content:"🔍";position:absolute;left:10px;top:50%;transform:translateY(-50%);font-size:.85rem;pointer-events:none;z-index:1}}
  .hist-count{{font-size:.82rem;color:#aaa;margin-bottom:8px}}
  .hist-table-wrap{{overflow-x:auto}}
  .hist-table th{{background:#FC4C02;color:white;padding:10px 12px;text-align:left;white-space:nowrap}}
  .hist-table td{{padding:8px 12px;border-bottom:1px solid #f5f5f5;white-space:nowrap}}
  .hist-table tr:hover td{{background:#fff8f5}}
  .sport-badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:600;background:#fff3ef;color:#FC4C02}}
  .pagination{{display:flex;gap:6px;justify-content:center;margin-top:16px;flex-wrap:wrap}}
  .pagination button{{padding:6px 12px;border:1px solid #ddd;background:white;border-radius:6px;cursor:pointer;font-size:.85rem}}
  .pagination button.active{{background:#FC4C02;color:white;border-color:#FC4C02}}
  .pagination button:hover:not(.active){{background:#f5f5f5}}
  .btn-reset{{padding:8px 14px;background:#f5f5f5;border:1px solid #ddd;border-radius:6px;cursor:pointer;font-size:.85rem;color:#666}}
  .btn-reset:hover{{background:#ffe8df;border-color:#FC4C02;color:#FC4C02}}
  footer{{text-align:center;padding:18px;color:#ccc;font-size:.78rem}}
</style>
</head>
<body>
<header>
  <div style="font-size:2rem">🏃</div>
  <div><h1>Strava Dashboard</h1><p>Mis à jour le {now} · Fenêtre {MIN_YEAR}–{CURRENT_YEAR}</p></div>
</header>
<div class="stats-bar" id="statsBar"></div>
<nav class="main-nav">
  <button class="active" onclick="showTab('t1',this)">🎯 Goals</button>
  <button onclick="showTab('t2',this)">🏅 Par sport</button>
  <button onclick="showTab('t3',this)">📈 Progression cumulée</button>
  <button onclick="showTab('t4',this)">🗓️ Tableau comparatif</button>
  <button onclick="showTab('t5',this)">🏆 Records personnels</button>
  <button onclick="showTab('t6',this)">📚 Historique complet</button>
</nav>
<main>
  <div id="t1" class="tab active">{goals_html}</div>
  <div id="t2" class="tab">
    <nav class="sport-nav" id="sportNav">{sports_tabs}</nav>
    <div style="margin-top:20px">{sports_panels}</div>
  </div>
  <div id="t3" class="tab">
    <div class="card">
      <h2 style="margin-bottom:16px">📊 Toutes activités — Distance cumulée · {MIN_YEAR}–{CURRENT_YEAR}</h2>
      <canvas id="chartCumul" height="90"></canvas>
    </div>
    <div id="cumulBySport"></div>
  </div>
  <div id="t4" class="tab">
    <div class="card">
      <div class="card-header"><h2>📊 Toutes activités — Tableau comparatif · {MIN_YEAR}–{CURRENT_YEAR}</h2></div>
      <div id="tableContainer" style="overflow-x:auto"></div>
    </div>
    <div id="tableBySport"></div>
  </div>
  <div id="t5" class="tab">{records_html}</div>
  <div id="t6" class="tab">
    <div class="card">
      <div class="hist-filters">
        <div class="search-wrap search-icon">
          <input type="text" id="histSearch" placeholder="Rechercher une activité..." oninput="filterHist()">
        </div>
        <label>Sport
          <select id="histSport" onchange="filterHist()">
            <option value="">Tous</option>
          </select>
        </label>
        <label>Année
          <select id="histAnnee" onchange="filterHist()">
            <option value="">Toutes</option>
          </select>
        </label>
        <label>Mois
          <select id="histMois" onchange="filterHist()">
            <option value="">Tous</option>
          </select>
        </label>
        <label>Distance min (km)
          <input type="number" id="histDistMin" placeholder="0" min="0" step="1" oninput="filterHist()">
        </label>
        <label>Distance max (km)
          <input type="number" id="histDistMax" placeholder="∞" min="0" step="1" oninput="filterHist()">
        </label>
        <button class="btn-reset" onclick="resetFilters()">✕ Réinitialiser</button>
      </div>
      <div class="hist-count" id="histCount"></div>
      <div class="hist-table-wrap">
        <table class="hist-table" id="histTable">
          <thead><tr>
            <th onclick="sortHist('date')">Date ↕</th>
            <th onclick="sortHist('sport')">Sport ↕</th>
            <th>Nom</th>
            <th onclick="sortHist('km')">Distance ↕</th>
            <th onclick="sortHist('duree_m')">Durée ↕</th>
            <th onclick="sortHist('fc')">FC moy. ↕</th>
            <th onclick="sortHist('vit')">Vitesse ↕</th>
          </tr></thead>
          <tbody id="histBody"></tbody>
        </table>
      </div>
      <div class="pagination" id="histPagination"></div>
    </div>
  </div>
</main>
<footer>Strava Dashboard · {CURRENT_YEAR} · données personnelles</footer>

<script>
const DATA = {json.dumps(data, ensure_ascii=False, default=str)};
const MOIS = {json.dumps(MOIS_LONG)};
const PER_PAGE = 50;

// ── Stats bar ──────────────────────────────────
const bar = document.getElementById("statsBar");
const gt  = DATA.stats_info.global_trend;
DATA.stats_info.stats.forEach(s => {{
  bar.innerHTML += `<div class="stat"><div class="val">${{s.km}} km</div><div class="lbl">Distance</div><div class="yr">${{s.annee}}</div></div>
    <div class="stat"><div class="val">${{s.activites}}</div><div class="lbl">Activités</div><div class="yr">${{s.annee}}</div></div>
    <div class="stat"><div class="val">${{s.heures}}h</div><div class="lbl">Durée</div><div class="yr">${{s.annee}}</div></div>
    <div class="sep"></div>`;
}});
bar.innerHTML += `<div class="global-tag"><span class="tag" style="background:${{gt.couleur}}20;color:${{gt.couleur}};border:1px solid ${{gt.couleur}}40;padding:6px 14px">${{gt.icone}} Global : ${{gt.label}}</span></div>`;

// ── Navigation ─────────────────────────────────
function showTab(id, btn) {{
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll("nav.main-nav button").forEach(b => b.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}}
function showSportTab(sport, btn) {{
  document.querySelectorAll(".sport-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll("#sportNav button").forEach(b => b.classList.remove("active"));
  document.getElementById("sport_" + sport.replace(/ /g,"_")).classList.add("active");
  btn.classList.add("active");
}}

// ── Charts sport ───────────────────────────────
const LABELS = {json.dumps(MOIS_FR)};
DATA.sports_data.forEach((sd, idx) => {{
  new Chart(document.getElementById(`dist_${{idx}}`), {{
    type:"bar", data:{{labels:LABELS, datasets:sd.dist_datasets}},
    options:{{responsive:true,plugins:{{legend:{{position:"top"}}}},
      scales:{{x:{{grid:{{display:false}}}},y:{{beginAtZero:true,title:{{display:true,text:"km"}}}}}}}}
  }});
  if (sd.has_cardio) {{
    const el = document.getElementById(`cardio_${{idx}}`);
    if (el) new Chart(el, {{
      type:"line", data:{{labels:LABELS, datasets:sd.cardio_datasets}},
      options:{{responsive:true,plugins:{{legend:{{position:"top"}}}},
        scales:{{x:{{grid:{{display:false}}}},y:{{title:{{display:true,text:"bpm"}}}}}}}}
    }});
  }}
}});

// ── Helpers ────────────────────────────────────
function makeCumulChart(canvasId, cumData) {{
  new Chart(document.getElementById(canvasId), {{
    type:"line",
    data:{{labels:cumData.labels.map((l,i)=>i%7===0?l:""), datasets:cumData.datasets}},
    options:{{responsive:true,plugins:{{legend:{{position:"top"}}}},
      scales:{{x:{{ticks:{{maxRotation:45}}}},y:{{beginAtZero:true,title:{{display:true,text:"km cumulés"}}}}}}}}
  }});
}}

function makeTableHtml(t) {{
  const annees = t.annees;
  let html = "<table><thead><tr><th>Mois</th>";
  annees.forEach((a, i) => {{
    html += `<th>${{a}}</th>`;
    if (i > 0) html += `<th style="font-size:.78rem;background:#c43a00">vs ${{annees[i-1]}}</th>`;
  }});
  html += "</tr></thead><tbody>";
  t.rows.forEach(row => {{
    html += `<tr><td style="font-weight:500">${{row.mois}}</td>`;
    annees.forEach((a, i) => {{
      const d = row[a]||{{km:0,count:0}};
      html += `<td><b>${{d.km}} km</b><br><span class="cnt">${{d.count}} act.</span></td>`;
      if (i > 0) {{
        const cur = d.km, prev = (row[annees[i-1]]||{{km:0}}).km;
        const diff = cur - prev;
        const pct  = prev > 0 ? Math.round(diff/prev*100) : null;
        html += pct === null
          ? `<td class="cnt">—</td>`
          : `<td class="${{diff>=0?'up':'down'}}" style="font-size:.82rem">${{diff>=0?'▲':'▼'}} ${{Math.abs(pct)}}%</td>`;
      }}
    }});
    html += "</tr>";
  }});
  return html + "</tbody></table>";
}}

// ── Cumul total ────────────────────────────────
makeCumulChart("chartCumul", DATA.cumulative.total);

// ── Cumul par sport ────────────────────────────
(function() {{
  const container = document.getElementById("cumulBySport");
  let chartIdx = 100;
  Object.entries(DATA.cumulative.by_sport).forEach(([sport, cumData]) => {{
    const id = `cumul_sport_${{chartIdx++}}`;
    container.innerHTML += `<div class="card" style="margin-top:18px">
      <h2 style="margin-bottom:16px">${{sport}} — Distance cumulée</h2>
      <canvas id="${{id}}" height="90"></canvas></div>`;
    setTimeout(() => makeCumulChart(id, cumData), 0);
  }});
}})();

// ── Tableau total ──────────────────────────────
document.getElementById("tableContainer").innerHTML = makeTableHtml(DATA.table.total);

// ── Tableau par sport ──────────────────────────
(function() {{
  const container = document.getElementById("tableBySport");
  Object.entries(DATA.table.by_sport).forEach(([sport, t]) => {{
    container.innerHTML += `<div class="card" style="margin-top:18px">
      <div class="card-header"><h2>${{sport}} — Tableau comparatif</h2></div>
      <div style="overflow-x:auto">${{makeTableHtml(t)}}</div></div>`;
  }});
}})();

// ── Historique ─────────────────────────────────
const HIST = DATA.history;
let histFiltered = [...HIST.rows];
let histPage = 1;
let histSort = {{key:"date", asc:false}};

// Peupler les dropdowns
const sportSel  = document.getElementById("histSport");
const anneeSel  = document.getElementById("histAnnee");
const moisSel   = document.getElementById("histMois");
HIST.sports.forEach(s => sportSel.innerHTML += `<option value="${{s}}">${{s}}</option>`);
HIST.annees.forEach(a => anneeSel.innerHTML += `<option value="${{a}}">${{a}}</option>`);
MOIS.forEach((m,i) => moisSel.innerHTML += `<option value="${{i+1}}">${{m}}</option>`);

function filterHist() {{
  const search   = document.getElementById("histSearch").value.toLowerCase();
  const sport    = document.getElementById("histSport").value;
  const annee    = parseInt(document.getElementById("histAnnee").value)||0;
  const mois     = parseInt(document.getElementById("histMois").value)||0;
  const distMin  = parseFloat(document.getElementById("histDistMin").value)||0;
  const distMax  = parseFloat(document.getElementById("histDistMax").value)||Infinity;

  histFiltered = HIST.rows.filter(r => {{
    if (sport && r.sport !== sport) return false;
    if (annee && r.annee !== annee) return false;
    if (mois  && r.mois  !== mois)  return false;
    if (r.km < distMin || r.km > distMax) return false;
    if (search && !r.nom.toLowerCase().includes(search) &&
        !r.sport.toLowerCase().includes(search) &&
        !r.date.includes(search)) return false;
    return true;
  }});

  // Tri
  histFiltered.sort((a,b) => {{
    let av = a[histSort.key], bv = b[histSort.key];
    if (av == null) av = histSort.asc ? Infinity : -Infinity;
    if (bv == null) bv = histSort.asc ? Infinity : -Infinity;
    return histSort.asc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
  }});

  histPage = 1;
  renderHist();
}}

function sortHist(key) {{
  if (histSort.key === key) histSort.asc = !histSort.asc;
  else {{ histSort.key = key; histSort.asc = false; }}
  filterHist();
}}

function resetFilters() {{
  document.getElementById("histSearch").value = "";
  document.getElementById("histSport").value  = "";
  document.getElementById("histAnnee").value  = "";
  document.getElementById("histMois").value   = "";
  document.getElementById("histDistMin").value = "";
  document.getElementById("histDistMax").value = "";
  filterHist();
}}

function renderHist() {{
  const total  = histFiltered.length;
  const pages  = Math.ceil(total / PER_PAGE);
  const start  = (histPage - 1) * PER_PAGE;
  const slice  = histFiltered.slice(start, start + PER_PAGE);

  document.getElementById("histCount").textContent =
    `${{total.toLocaleString()}} activité${{total>1?'s':''}} trouvée${{total>1?'s':''}}`;

  let html = "";
  slice.forEach(r => {{
    const fc  = r.fc  ? `${{r.fc}} bpm`  : "—";
    const vit = r.vit ? `${{r.vit}} km/h` : "—";
    html += `<tr>
      <td>${{r.date}}</td>
      <td><span class="sport-badge">${{r.sport}}</span></td>
      <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis">${{r.nom}}</td>
      <td><b>${{r.km}} km</b></td>
      <td>${{r.duree}}</td>
      <td>${{fc}}</td>
      <td>${{vit}}</td>
    </tr>`;
  }});
  document.getElementById("histBody").innerHTML = html;

  // Pagination
  let pag = "";
  if (histPage > 1) pag += `<button onclick="goPage(${{histPage-1}})">‹</button>`;
  const range = 2;
  for (let p = Math.max(1,histPage-range); p <= Math.min(pages,histPage+range); p++) {{
    pag += `<button class="${{p===histPage?'active':''}}" onclick="goPage(${{p}})">${{p}}</button>`;
  }}
  if (histPage < pages) pag += `<button onclick="goPage(${{histPage+1}})">›</button>`;
  if (pages > 1) pag += `<span style="font-size:.8rem;color:#aaa;align-self:center">Page ${{histPage}}/${{pages}}</span>`;
  document.getElementById("histPagination").innerHTML = pag;
}}

function goPage(p) {{ histPage = p; renderHist(); window.scrollTo(0,0); }}

// Init historique
filterHist();
</script>
</body>
</html>"""

if __name__ == "__main__":
    if not os.path.exists(CSV_FILE):
        print(f"❌ Fichier introuvable : {CSV_FILE}"); exit(1)

    print(f"📊 Génération du dashboard ({MIN_YEAR}–{CURRENT_YEAR})...")
    df_full = load_data()
    df_win  = window(df_full)

    sports = top_sports(df_win, n=5)
    print(f"   Sports : {', '.join(sports)}")
    print(f"   Total activités : {len(df_full)} ({len(df_win)} dans la fenêtre 5 ans)")

    data = {
        "sports_data": [build_sport_data(df_win, df_full, s) for s in sports],
        "cumulative":  build_cumulative(df_win, sports),
        "table":       build_table(df_win, sports),
        "stats_info":  build_stats(df_win, df_full),
        "goals":       build_goals(df_full),
        "records":     build_personal_bests(df_win),
        "history":     build_history(df_full),
    }

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(generate_html(data))

    print(f"✅ Dashboard généré : {OUT_FILE}")
    import webbrowser
    webbrowser.open(f"file://{OUT_FILE}")
