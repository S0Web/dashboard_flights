"""
Dashboard Trafic aérien NYC — Streamlit + Supabase (PostgreSQL)
Lancer :  streamlit run app.py
"""
from decimal import Decimal
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Trafic aérien NYC", page_icon="✈️", layout="wide")
import time as _time
_T0 = _time.time()

def log(msg):
    print(f"[debug {_time.time() - _T0:6.1f}s] {msg}", flush=True)

log("démarrage du script")

# --------------------------------------------------------------------------
# Connexion : .streamlit/secrets.toml doit contenir
#   [supabase]
#   project_ref = "xxxxxxxx"      (l'identifiant dans l'URL du projet)
#   password    = "mot de passe de la base"
#   host        = "..."           (optionnel : sinon trouvé automatiquement)
# --------------------------------------------------------------------------
REGIONS = ["eu-west-3", "eu-central-1", "eu-west-1", "eu-west-2", "eu-north-1",
           "eu-central-2", "us-east-1", "us-east-2", "us-west-1", "us-west-2",
           "ca-central-1", "sa-east-1", "ap-southeast-1", "ap-southeast-2",
           "ap-northeast-1", "ap-northeast-2", "ap-south-1"]


@st.cache_resource(show_spinner="Connexion à Supabase…")
def get_engine():
    cfg = st.secrets["supabase"]
    ref, pwd = cfg["project_ref"].strip(), quote_plus(cfg["password"])
    if "host" in cfg:
        hosts = [cfg["host"]]
    else:  # Session pooler (IPv4) : on teste les régions jusqu'à trouver la bonne
        hosts = [f"{p}-{r}.pooler.supabase.com" for p in ("aws-0", "aws-1") for r in REGIONS]
    last_err = None
    for host in hosts:
        log(f"connexion à {host}...")
        engine = create_engine(
            f"postgresql+psycopg2://postgres.{ref}:{pwd}@{host}:5432/postgres",
            connect_args={"sslmode": "require", "connect_timeout": 5},
            pool_pre_ping=True,
        )
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            log("connexion OK")
            return engine, host
        except Exception as e:
            last_err = e
            log(f"échec connexion : {e}")
            engine.dispose()
            if "password authentication failed" in str(e):
                break  # bonne région mais mauvais mot de passe : inutile de continuer
    st.error(f"Connexion impossible à Supabase.\n\nDernière erreur : {last_err}")
    st.stop()


engine, HOST = get_engine()


@st.cache_data(ttl=3600, show_spinner=False)
def _run(sql: str, params: dict) -> pd.DataFrame:
    log("requête : " + " ".join(sql.split())[:80])
    with engine.connect() as c:
        df = pd.read_sql(text(sql), c, params=params)
    log(f"  -> {len(df)} lignes")
    return df


def q(sql: str, **params) -> pd.DataFrame:
    """Exécute une requête SQL (résultat mis en cache 1 h).
    avg()/round() renvoient du NUMERIC Postgres -> Decimal Python : on convertit en float."""
    df = _run(sql, params).copy()
    for col in df.select_dtypes("object").columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


MOIS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
        "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
JOURS = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]  # extract(dow) : 0 = dimanche


# --------------------------------------------------------------------------
# Tables "typées" : selon l'import, les colonnes peuvent être en TEXT (avec des
# valeurs vides ou 'NA'). On convertit tout proprement avant de calculer.
# --------------------------------------------------------------------------
def _n(c: str, cast: str = "numeric") -> str:
    """Colonne numérique : '' / 'NA' -> NULL, puis conversion."""
    chain = "::numeric::int" if cast == "int" else f"::{cast}"
    return f"NULLIF(NULLIF(trim({c}::text), ''), 'NA'){chain} AS {c}"


def _t(c: str) -> str:
    """Colonne texte nettoyée."""
    return f"NULLIF(NULLIF(trim({c}::text), ''), 'NA') AS {c}"


FL = ("(SELECT " + ", ".join(
        [_n(c, "int") for c in ("year", "month", "day", "hour")]
        + [_n(c) for c in ("dep_time", "dep_delay", "arr_delay", "distance")]
        + [_t(c) for c in ("carrier", "tailnum", "origin", "dest")])
      + " FROM flights)")
AL = "(SELECT " + ", ".join([_t("carrier"), _t("name")]) + " FROM airlines)"
AP = ("(SELECT " + ", ".join([_t("faa"), _t("name"), _n("lat", "float"), _n("lon", "float")])
      + " FROM airports)")
PL = ("(SELECT " + ", ".join([_t("tailnum"), _t("manufacturer"), _n("year", "int")])
      + " FROM planes)")
WX = ("(SELECT " + ", ".join(
        [_t("origin")] + [_n(c, "int") for c in ("year", "month", "day", "hour")]
        + [_n(c, "float") for c in ("visib", "wind_speed", "precip", "temp", "humid")])
      + " FROM weather)")

# --------------------------------------------------------------------------
# Filtres (barre latérale)
# --------------------------------------------------------------------------
airlines = q(f"SELECT carrier, name FROM {AL} a WHERE carrier IS NOT NULL ORDER BY name")
origins = q(f"""
    SELECT faa, name FROM {AP} ap
    WHERE faa IN (SELECT DISTINCT origin FROM {FL} f)
    ORDER BY faa
""")

st.sidebar.title("✈️ Filtres")
sel_origins = st.sidebar.multiselect(
    "Aéroport de départ",
    options=origins["faa"].tolist(),
    default=origins["faa"].tolist(),
    format_func=lambda c: f"{c} – {origins.set_index('faa').loc[c, 'name']}",
)
sel_carriers = st.sidebar.multiselect(
    "Compagnies",
    options=airlines["carrier"].tolist(),
    default=airlines["carrier"].tolist(),
    format_func=lambda c: airlines.set_index("carrier").loc[c, "name"],
)
m0, m1 = st.sidebar.select_slider(
    "Période (mois)", options=list(range(1, 13)), value=(1, 12),
    format_func=lambda m: MOIS[m - 1],
)
st.sidebar.caption("Retard « à l'heure » = arrivée avec ≤ 15 min de retard.")
st.sidebar.caption(f"🔌 Connecté via {HOST}")

if not sel_origins or not sel_carriers:
    st.warning("Sélectionne au moins un aéroport et une compagnie.")
    st.stop()

# Clause WHERE commune à toutes les requêtes sur flights (alias f)
W = "f.origin = ANY(:origins) AND f.carrier = ANY(:carriers) AND f.month BETWEEN :m0 AND :m1"
P = dict(origins=sel_origins, carriers=sel_carriers, m0=m0, m1=m1)

# --------------------------------------------------------------------------
# En-tête + KPI
# --------------------------------------------------------------------------
st.title("Trafic aérien au départ de New York")
st.caption("Source : base Supabase — tables flights, airlines, airports, planes, weather")

kpi = q(f"""
    SELECT count(*)                                              AS vols,
           avg((f.dep_time IS NULL)::int) * 100                           AS pct_annules,
           avg(f.dep_delay)                                      AS retard_dep,
           avg((f.arr_delay <= 15)::int) * 100                   AS pct_heure,
           count(DISTINCT f.dest)                                AS destinations
    FROM {FL} f WHERE {W}
""", **P).iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Vols", f"{int(kpi.vols):,}".replace(",", " "))
c2.metric("Destinations", int(kpi.destinations))
c3.metric("Retard moyen au départ", f"{kpi.retard_dep:.1f} min")
c4.metric("Vols à l'heure", f"{kpi.pct_heure:.1f} %")
c5.metric("Vols annulés", f"{kpi.pct_annules:.1f} %")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📈 Vue d'ensemble", "⏱️ Retards", "🏢 Compagnies",
     "🗺️ Destinations", "🌦️ Météo", "🛩️ Flotte"]
)

# --------------------------------------------------------------------------
# 1. Vue d'ensemble
# --------------------------------------------------------------------------
with tab1:
    mensuel = q(f"""
        SELECT f.month, f.origin, count(*) AS vols
        FROM {FL} f WHERE {W}
        GROUP BY 1, 2 ORDER BY 1
    """, **P)
    mensuel["mois"] = mensuel["month"].map(lambda m: MOIS[m - 1])
    fig = px.line(mensuel, x="mois", y="vols", color="origin", markers=True,
                  title="Nombre de vols par mois et par aéroport",
                  labels={"mois": "", "vols": "Vols", "origin": "Aéroport"})
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns(2)
    par_origine = q(f"""
        SELECT f.origin, count(*) AS vols
        FROM {FL} f WHERE {W} GROUP BY 1 ORDER BY 2 DESC
    """, **P)
    col_a.plotly_chart(
        px.pie(par_origine, names="origin", values="vols", hole=0.5,
               title="Répartition des vols par aéroport"),
        use_container_width=True)

    statut = q(f"""
        SELECT CASE WHEN f.dep_time IS NULL THEN 'Annulé'
                    WHEN f.arr_delay IS NULL THEN 'Dérouté'
                    WHEN f.arr_delay <= 15 THEN 'À l''heure'
                    ELSE 'En retard (> 15 min)' END AS statut,
               count(*) AS vols
        FROM {FL} f WHERE {W} GROUP BY 1 ORDER BY 2 DESC
    """, **P)
    col_b.plotly_chart(
        px.bar(statut, x="statut", y="vols", color="statut",
               title="Statut des vols", labels={"statut": "", "vols": "Vols"}),
        use_container_width=True)

# --------------------------------------------------------------------------
# 2. Retards
# --------------------------------------------------------------------------
with tab2:
    par_heure = q(f"""
        SELECT f.hour AS heure, avg(f.dep_delay) AS retard_moyen, count(*) AS vols
        FROM {FL} f WHERE {W} AND f.dep_time IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """, **P)
    st.plotly_chart(
        px.bar(par_heure, x="heure", y="retard_moyen", hover_data=["vols"],
               title="Retard moyen au départ selon l'heure programmée",
               labels={"heure": "Heure de départ programmée",
                       "retard_moyen": "Retard moyen (min)"}),
        use_container_width=True)

    col_a, col_b = st.columns(2)
    par_jour = q(f"""
        SELECT extract(dow FROM make_date(f.year, f.month, f.day))::int AS dow, avg(f.dep_delay) AS retard_moyen
        FROM {FL} f WHERE {W} AND f.dep_time IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """, **P)
    par_jour["jour"] = par_jour["dow"].map(lambda d: JOURS[d])
    col_a.plotly_chart(
        px.bar(par_jour, x="jour", y="retard_moyen",
               title="Retard moyen par jour de la semaine",
               labels={"jour": "", "retard_moyen": "Retard moyen (min)"}),
        use_container_width=True)

    tranches = q(f"""
        SELECT CASE WHEN f.dep_delay <= 0   THEN '1. En avance / à l''heure'
                    WHEN f.dep_delay <= 15  THEN '2. 1–15 min'
                    WHEN f.dep_delay <= 60  THEN '3. 16–60 min'
                    WHEN f.dep_delay <= 180 THEN '4. 1–3 h'
                    ELSE '5. > 3 h' END AS tranche,
               count(*) AS vols
        FROM {FL} f WHERE {W} AND f.dep_delay IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """, **P)
    col_b.plotly_chart(
        px.bar(tranches, x="tranche", y="vols",
               title="Distribution des retards au départ",
               labels={"tranche": "", "vols": "Vols"}),
        use_container_width=True)

# --------------------------------------------------------------------------
# 3. Compagnies
# --------------------------------------------------------------------------
with tab3:
    compagnies = q(f"""
        SELECT a.name AS compagnie,
               count(*)                               AS vols,
               round(avg(f.dep_delay)::numeric, 1)    AS retard_moyen_dep,
               round(avg(f.arr_delay)::numeric, 1)    AS retard_moyen_arr,
               round(avg((f.arr_delay <= 15)::int)::numeric * 100, 1) AS pct_a_l_heure,
               round(avg((f.dep_time IS NULL)::int)::numeric * 100, 2)        AS pct_annules
        FROM {FL} f JOIN {AL} a ON a.carrier = f.carrier
        WHERE {W}
        GROUP BY a.name ORDER BY vols DESC
    """, **P)
    col_a, col_b = st.columns(2)
    col_a.plotly_chart(
        px.bar(compagnies.sort_values("vols"), x="vols", y="compagnie",
               orientation="h", title="Volume de vols par compagnie",
               labels={"compagnie": "", "vols": "Vols"}),
        use_container_width=True)
    col_b.plotly_chart(
        px.scatter(compagnies, x="retard_moyen_dep", y="pct_a_l_heure",
                   size="vols", color="compagnie", size_max=50,
                   title="Ponctualité vs retard moyen (taille = volume)",
                   labels={"retard_moyen_dep": "Retard moyen au départ (min)",
                           "pct_a_l_heure": "% vols à l'heure"}),
        use_container_width=True)
    st.dataframe(compagnies, use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------
# 4. Destinations
# --------------------------------------------------------------------------
with tab4:
    dest = q(f"""
        SELECT f.dest, ap.name, ap.lat, ap.lon,
               count(*) AS vols, round(avg(f.arr_delay)::numeric, 1) AS retard_moyen_arr,
               round(avg(f.distance)) AS distance
        FROM {FL} f JOIN {AP} ap ON ap.faa = f.dest
        WHERE {W}
        GROUP BY f.dest, ap.name, ap.lat, ap.lon
        ORDER BY vols DESC
    """, **P)
    fig = px.scatter_geo(dest, lat="lat", lon="lon", size="vols",
                         color="retard_moyen_arr", hover_name="name",
                         hover_data={"dest": True, "vols": True, "distance": True,
                                     "lat": False, "lon": False},
                         color_continuous_scale="RdYlGn_r", scope="usa",
                         title="Destinations (taille = nombre de vols, couleur = retard moyen à l'arrivée)",
                         labels={"retard_moyen_arr": "Retard (min)"})
    fig.update_layout(height=550, margin=dict(l=0, r=0, t=50, b=0))
    st.plotly_chart(fig, use_container_width=True)

    n = st.slider("Nombre de destinations à afficher", 5, 30, 15)
    top = dest.head(n)
    st.plotly_chart(
        px.bar(top.sort_values("vols"), x="vols", y="name", orientation="h",
               hover_data=["dest", "distance"],
               title=f"Top {n} des destinations",
               labels={"name": "", "vols": "Vols"}),
        use_container_width=True)

# --------------------------------------------------------------------------
# 5. Météo
# --------------------------------------------------------------------------
with tab5:
    st.caption("Jointure flights × weather sur aéroport + date + heure de départ programmée "
               "(seuls les vols ayant un relevé météo à cette heure sont pris en compte).")
    meteo_var = st.selectbox(
        "Variable météo",
        options=["visib", "wind_speed", "precip", "temp", "humid"],
        format_func={"visib": "Visibilité (miles)", "wind_speed": "Vitesse du vent (mph)",
                     "precip": "Précipitations (pouces)", "temp": "Température (°F)",
                     "humid": "Humidité (%)"}.get,
    )
    # La colonne est choisie dans une liste fermée -> pas de risque d'injection
    meteo = q(f"""
        WITH j AS (
            SELECT f.dep_delay, w.{meteo_var} AS val
            FROM {FL} f
            JOIN {WX} w ON w.origin = f.origin AND w.year = f.year
                          AND w.month = f.month AND w.day = f.day AND w.hour = f.hour
            WHERE {W} AND f.dep_delay IS NOT NULL AND w.{meteo_var} IS NOT NULL
        )
        SELECT width_bucket(val, (SELECT min(val) FROM j), (SELECT max(val) FROM j) + 1e-6, 10) AS bucket,
               round(min(val)::numeric, 2) AS de, round(max(val)::numeric, 2) AS a,
               avg(dep_delay) AS retard_moyen, count(*) AS vols
        FROM j GROUP BY 1 ORDER BY 1
    """, **P)
    meteo["tranche"] = meteo["de"].astype(str) + " – " + meteo["a"].astype(str)
    st.plotly_chart(
        px.bar(meteo, x="tranche", y="retard_moyen", hover_data=["vols"],
               title="Retard moyen au départ selon la météo",
               labels={"tranche": "", "retard_moyen": "Retard moyen (min)"}),
        use_container_width=True)

# --------------------------------------------------------------------------
# 6. Flotte
# --------------------------------------------------------------------------
with tab6:
    col_a, col_b = st.columns(2)
    constructeurs = q(f"""
        SELECT p.manufacturer AS constructeur, count(DISTINCT p.tailnum) AS avions,
               count(*) AS vols
        FROM {FL} f JOIN {PL} p ON p.tailnum = f.tailnum
        WHERE {W}
        GROUP BY 1 ORDER BY avions DESC LIMIT 10
    """, **P)
    col_a.plotly_chart(
        px.bar(constructeurs.sort_values("avions"), x="avions", y="constructeur",
               orientation="h", hover_data=["vols"],
               title="Top 10 constructeurs (avions utilisés)",
               labels={"constructeur": "", "avions": "Avions"}),
        use_container_width=True)

    age = q(f"""
        SELECT f.year - p.year AS age, avg(f.dep_delay) AS retard_moyen,
               count(*) AS vols
        FROM {FL} f JOIN {PL} p ON p.tailnum = f.tailnum
        WHERE {W} AND p.year IS NOT NULL AND f.dep_delay IS NOT NULL
        GROUP BY 1 HAVING count(*) >= 100 ORDER BY 1
    """, **P)
    col_b.plotly_chart(
        px.line(age, x="age", y="retard_moyen", markers=True, hover_data=["vols"],
                title="Retard moyen selon l'âge de l'avion",
                labels={"age": "Âge (années)", "retard_moyen": "Retard moyen (min)"}),
        use_container_width=True)
