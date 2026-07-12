#!/usr/bin/env python3
"""
Dashboard Político — Alcance & Engajamento (+ Funil de Vídeo)
Gera index.html standalone a partir do Google Sheets (aba meta-ads).
"""

import pandas as pd, json, re, hashlib, requests
from datetime import date
from pathlib import Path

# ══════════════════════════════════════════════════════
# CONFIG DO CLIENTE — edite apenas esta seção
# ══════════════════════════════════════════════════════
SHEET_ID       = "1enwKvr8k_kIUQslpGeBGPODksGka_E2_UKL2jWUBvS4"
TEMPLATE_FILE  = "dashboard.html"
OUTPUT_FILE    = "index.html"

NOME_CLIENTE   = "Daniel Mussi"
LOGO_LETRA     = "DM"
LOGO_URL       = "logo.png"  # arquivo de imagem (coloque junto do index.html); deixe "" para usar só a letra
COR_ACENTO     = "#0064e0"

AGENCY_NOME      = ""  # preencha se quiser mostrar o nome em texto quando não houver logo
AGENCY_LOGO_URL  = "logo.png"  # logo da agência no rodapé; deixe "" para mostrar só o nome

MOEDA          = "BRL"     # BRL | USD | EUR | ARS
_MOEDA_MAP = {
    "BRL": {"simbolo": "R$", "locale": "pt-BR"},
    "USD": {"simbolo": "$",  "locale": "en-US"},
    "EUR": {"simbolo": "€",  "locale": "de-DE"},
    "ARS": {"simbolo": "$",  "locale": "es-AR"},
}
_moeda_cfg    = _MOEDA_MAP.get(MOEDA, _MOEDA_MAP["BRL"])
MOEDA_SIMBOLO = _moeda_cfg["simbolo"]

# ══════════════════════════════════════════════════════
def sheet_url(t): return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={t}"
URL_META = sheet_url("meta-ads")
URL_BD_AGE_GENDER = sheet_url("breakdown-gender-age")
URL_BD_PLATFORM = sheet_url("breakdown-platform")

def to_num(s):
    if pd.api.types.is_numeric_dtype(s): return s.fillna(0)
    clean = s.astype(str).str.strip().str.replace("R$", "", regex=False).str.strip()
    if clean.str.contains(r"\d,\d", regex=True).any():
        clean = clean.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(clean, errors="coerce").fillna(0)

def download_thumb(url, d):
    if not url or str(url) == "nan": return ""
    try:
        ext = ".png" if ".png" in url.lower() else ".jpg"
        fname = hashlib.md5(url.encode()).hexdigest()[:16] + ext
        fp = d / fname
        if not fp.exists():
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200: fp.write_bytes(r.content)
            else: return ""
        return "imgs/" + fname
    except Exception:
        return ""

VIDEO_COLS = {
    "Video 15 Sec Watched Actions": "v15",
    "Video 25 Percent Watched Actions": "v25",
    "Video 50 Percent Watched Actions": "v50",
    "Video 75 Percent Watched Actions": "v75",
    "Video 95 Percent Watched Actions": "v95",
    "Video 100 Percent Watched Actions": "v100",
    "Video Thruplay Watched Actions": "thruplay",
}

def load_meta():
    print("  Lendo meta-ads...")
    df = pd.read_csv(URL_META)
    df = df.rename(columns={
        "Date": "date", "Campaign Name": "campaign", "Adset Name": "adset",
        "Ad Name": "ad", "Thumbnail URL": "thumb", "Status": "status",
        "Spend (Cost, Amount Spent)": "spend", "Impressions": "impressions",
        "Reach (Estimated)": "reach",
        "Action Post Reactions": "reactions",
        "Action Post Shares": "shares",
        "Action Post Comments": "comments",
        "Action Post Save (Onsite Conversion)": "saves",
        "Instagram Profile Visits": "profile_visits",
        "Clicks": "clicks",
        **VIDEO_COLS,
    })
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "status" not in df.columns: df["status"] = ""
    df["status"] = df["status"].astype(str).str.strip().str.upper()
    for c in ["spend", "impressions", "reach", "reactions", "shares", "comments", "saves", "profile_visits", "clicks",
              "v15", "v25", "v50", "v75", "v95", "v100", "thruplay"]:
        if c in df.columns: df[c] = to_num(df[c])
        else: df[c] = 0
    df["engajamento"] = df["reactions"] + df["shares"] + df["comments"] + df["saves"]
    df = df.dropna(subset=["date"])
    print(f"     {len(df)} linhas | {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"     Alcance total: {df['reach'].sum():.0f} | Engajamento total: {df['engajamento'].sum():.0f}")
    return df

def calc_kpis(p):
    sp = float(p["spend"].sum()); imp = float(p["impressions"].sum())
    rch = float(p["reach"].sum())
    reac = float(p["reactions"].sum()); sha = float(p["shares"].sum())
    com = float(p["comments"].sum()); sav = float(p["saves"].sum())
    pv = float(p["profile_visits"].sum())
    eng = reac + sha + com + sav
    return {
        "spend": round(sp, 2), "impressions": int(imp), "reach": int(rch),
        "reactions": int(reac), "shares": int(sha), "comments": int(com), "saves": int(sav),
        "profile_visits": int(pv),
        "engajamento": int(eng),
        "cpm": round(sp / imp * 1000, 2) if imp > 0 else None,
        "cpe": round(sp / eng, 2) if eng > 0 else None,
        "taxa_eng": round(eng / rch * 100, 2) if rch > 0 else None,
        "video": {
            "v15": int(p["v15"].sum()), "v25": int(p["v25"].sum()), "v50": int(p["v50"].sum()),
            "v75": int(p["v75"].sum()), "v95": int(p["v95"].sum()), "v100": int(p["v100"].sum()),
            "thruplay": int(p["thruplay"].sum()),
            "video_impressions": video_impressions(p),
        },
    }

def build_daily(p):
    agg = p.groupby("date").agg(
        spend=("spend", "sum"), impressions=("impressions", "sum"), reach=("reach", "sum"),
        reactions=("reactions", "sum"), shares=("shares", "sum"),
        comments=("comments", "sum"), saves=("saves", "sum"), engajamento=("engajamento", "sum"),
    ).reset_index().sort_values("date")
    out = {k: [] for k in ["days", "spend", "impressions", "reach", "engajamento",
                            "reactions", "shares", "comments", "saves", "cpm", "cpe"]}
    for _, r in agg.iterrows():
        sp = float(r["spend"]); imp = float(r["impressions"]); eg = float(r["engajamento"])
        out["days"].append(r["date"].strftime("%d/%m/%Y"))
        out["spend"].append(round(sp, 2))
        out["impressions"].append(int(imp))
        out["reach"].append(int(r["reach"]))
        out["engajamento"].append(int(eg))
        out["reactions"].append(int(r["reactions"]))
        out["shares"].append(int(r["shares"]))
        out["comments"].append(int(r["comments"]))
        out["saves"].append(int(r["saves"]))
        out["cpm"].append(round(sp / imp * 1000, 2) if imp > 0 else None)
        out["cpe"].append(round(sp / eg, 2) if eg > 0 else None)
    return out

def video_impressions(p):
    """Soma impressões somente dos anúncios que são vídeo (tiveram ao menos
    1 VV15s no recorte). Anúncios de imagem (sem nenhum VV15s) são excluídos
    da base do funil, senão o % fica artificialmente baixo."""
    g = p.groupby(["campaign", "adset", "ad"]).agg(v15=("v15", "sum"), imp=("impressions", "sum")).reset_index()
    return int(g[g["v15"] > 0]["imp"].sum())

def load_breakdown(url, dim_cols):
    try:
        df = pd.read_csv(url)
        rename = {
            "Date": "date", "Spend (Cost, Amount Spent)": "spend",
            "Reach (Estimated)": "reach", "Impressions": "impressions",
            "Action Post Engagement": "engagement",
        }
        rename.update(dim_cols)
        df = df.rename(columns=rename)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for c in ["spend", "reach", "impressions", "engagement"]:
            if c in df.columns: df[c] = to_num(df[c])
            else: df[c] = 0
        df = df.dropna(subset=["date"])
        return df
    except Exception as e:
        print(f"  Aviso breakdown ({url}): {e}")
        return pd.DataFrame()

def build_bd_age_gender():
    print("  Lendo breakdown-gender-age...")
    df = load_breakdown(URL_BD_AGE_GENDER, {"Age (Breakdown)": "age", "Gender (Breakdown)": "gender"})
    if df.empty: return []
    rows = []
    for _, r in df.iterrows():
        rows.append({"d": r["date"].strftime("%d/%m/%Y"), "age": str(r.get("age", "")), "gen": str(r.get("gender", "")),
                     "sp": round(float(r["spend"]), 2), "imp": int(r["impressions"]), "rch": int(r["reach"]),
                     "eng": int(r["engagement"])})
    return rows

def build_bd_platform():
    print("  Lendo breakdown-platform...")
    df = load_breakdown(URL_BD_PLATFORM, {"Platform Position (Breakdown)": "platform"})
    if df.empty: return []
    rows = []
    for _, r in df.iterrows():
        rows.append({"d": r["date"].strftime("%d/%m/%Y"), "plat": str(r.get("platform", "")),
                     "sp": round(float(r["spend"]), 2), "imp": int(r["impressions"]), "rch": int(r["reach"]),
                     "eng": int(r["engagement"])})
    return rows


    hoje = pd.Timestamp(date.today())
    ranges = {"7": (hoje - pd.Timedelta(days=6), hoje), "14": (hoje - pd.Timedelta(days=13), hoje),
              "30": (hoje - pd.Timedelta(days=29), hoje), "all": (None, None)}
    out = {}
    for pname, (start, end) in ranges.items():
        p = df if start is None else df[(df["date"] >= start) & (df["date"] <= end)]
        out[pname] = calc_kpis(p)
    return out

def periods_kpis(df):
    hoje = pd.Timestamp(date.today())
    ranges = {"7": (hoje - pd.Timedelta(days=6), hoje), "14": (hoje - pd.Timedelta(days=13), hoje),
              "30": (hoje - pd.Timedelta(days=29), hoje), "all": (None, None)}
    out = {}
    for pname, (start, end) in ranges.items():
        p = df if start is None else df[(df["date"] >= start) & (df["date"] <= end)]
        out[pname] = calc_kpis(p)
    return out

def build_raw(df, img_dir):
    """Uma linha por (data, campanha, conjunto, anúncio) — usada para montar a
    lista de campanhas/conjuntos/criativos e o funil de vídeo no cliente (JS),
    respeitando o filtro de período escolhido pelo usuário."""
    df_thumb = df[df["thumb"].notna() & (df["thumb"].astype(str) != "nan")] if "thumb" in df.columns else pd.DataFrame()
    thumb_map = {}
    for _, r in df_thumb.iterrows():
        k = (str(r["ad"]), str(r["adset"]), str(r["campaign"]))
        if k not in thumb_map:
            thumb_map[k] = download_thumb(str(r["thumb"]), img_dir)
    agg = df.groupby(["date", "campaign", "adset", "ad"]).agg(
        spend=("spend", "sum"), impressions=("impressions", "sum"), reach=("reach", "sum"),
        reactions=("reactions", "sum"), shares=("shares", "sum"), comments=("comments", "sum"),
        saves=("saves", "sum"), clicks=("clicks", "sum"),
        v15=("v15", "sum"), v25=("v25", "sum"), v50=("v50", "sum"),
        v75=("v75", "sum"), v95=("v95", "sum"), v100=("v100", "sum"), thruplay=("thruplay", "sum"),
        status=("status", "last"),
    ).reset_index()
    rows = []
    for _, r in agg.iterrows():
        k = (str(r["ad"]), str(r["adset"]), str(r["campaign"]))
        rows.append({
            "d": r["date"].strftime("%d/%m/%Y"), "c": str(r["campaign"]), "a": str(r["adset"]),
            "ad": str(r["ad"]), "th": thumb_map.get(k, ""), "st": str(r["status"]),
            "sp": round(float(r["spend"]), 2), "imp": int(r["impressions"]), "rch": int(r["reach"]),
            "rc": int(r["reactions"]), "sh": int(r["shares"]), "cm": int(r["comments"]), "sv": int(r["saves"]),
            "cl": int(r["clicks"]),
            "v15": int(r["v15"]), "v25": int(r["v25"]), "v50": int(r["v50"]),
            "v75": int(r["v75"]), "v95": int(r["v95"]), "v100": int(r["v100"]), "tp": int(r["thruplay"]),
        })
    return rows

def replace_js_const(html, name, value):
    replacement = f"const {name} = {json.dumps(value, ensure_ascii=False)};"
    pattern_start = re.compile(rf"const {name}\s*=\s*")
    m = pattern_start.search(html)
    if not m:
        print(f"  AVISO: não encontrou const {name}")
        return html
    start = m.start(); val_start = m.end()
    i = val_start; depth = 0; in_str = False; str_char = None
    while i < len(html):
        ch = html[i]
        if in_str:
            if ch == '\\': i += 2; continue
            if ch == str_char: in_str = False
        else:
            if ch in ('"', "'", '`'): in_str = True; str_char = ch
            elif ch in ('{', '['): depth += 1
            elif ch in ('}', ']'): depth -= 1
            elif ch == ';' and depth == 0: break
        i += 1
    html = html[:start] + replacement + html[i+1:]
    return html

def main():
    print("=" * 60)
    print(f"Dashboard Político — {NOME_CLIENTE}")
    print("=" * 60)
    img_dir = Path("imgs"); img_dir.mkdir(exist_ok=True)

    df = load_meta()
    kpis_all = calc_kpis(df)
    kpis_periods = periods_kpis(df)
    daily = build_daily(df)
    raw = build_raw(df, img_dir)
    bd_age_gender = build_bd_age_gender()
    bd_platform = build_bd_platform()

    print("\n[HTML]")
    if not Path(TEMPLATE_FILE).exists():
        print(f"  ERRO: {TEMPLATE_FILE} não encontrado"); return

    html = Path(TEMPLATE_FILE).read_text(encoding="utf-8")
    html = replace_js_const(html, "KPIS_ALL",      kpis_all)
    html = replace_js_const(html, "KPIS_PERIODS",  kpis_periods)
    html = replace_js_const(html, "DAILY",         daily)
    html = replace_js_const(html, "RAW",           raw)
    html = replace_js_const(html, "BD_AGE_GENDER", bd_age_gender)
    html = replace_js_const(html, "BD_PLATFORM",   bd_platform)
    html = replace_js_const(html, "DATA_GERACAO",  date.today().strftime("%Y-%m-%d"))
    html = replace_js_const(html, "MOEDA_SIMBOLO", MOEDA_SIMBOLO)
    html = replace_js_const(html, "NOME_CLIENTE",  NOME_CLIENTE)
    html = replace_js_const(html, "LOGO_LETRA",    LOGO_LETRA)
    html = replace_js_const(html, "LOGO_URL",      LOGO_URL)
    html = replace_js_const(html, "AGENCY_NOME",     AGENCY_NOME)
    html = replace_js_const(html, "AGENCY_LOGO_URL", AGENCY_LOGO_URL)
    html = replace_js_const(html, "COR_ACENTO",    COR_ACENTO)

    Path(OUTPUT_FILE).write_text(html, encoding="utf-8")
    print(f"  ✓ {OUTPUT_FILE} ({len(html)//1024}KB)")
    print("=" * 60)

if __name__ == "__main__":
    main()
