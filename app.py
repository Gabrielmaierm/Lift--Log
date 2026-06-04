"""
app.py — LiftLog Dashboard
==========================
Rediseño visual completo: paleta oscura + dorado olímpico.
"""

import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from coach import ask_coach, build_athlete_context
from db import (
    COMPETITION_LEVELS,
    TRAINING_STATES,
    WEIGHT_CATEGORIES,
    delete_1rm,
    delete_session,
    get_1rm_history_by_movement,
    get_all_movements,
    get_athlete_profile,
    get_current_1rms,
    get_recent_sessions,
    get_snatch_cj_ratio,
    get_coach_history,
    get_volume_trend_alert,
    get_weekly_tonnage,
    initialize_db,
    insert_session,
    insert_set,
    profile_is_complete,
    save_athlete_profile,
    save_manual_1rm,
)

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="LiftLog",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialize_db()

# ─────────────────────────────────────────────────────────────
# CSS GLOBAL
# ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Variables ─────────────────────────────────────────── */
:root {
    --gold:     #C9A84C;
    --gold-dim: #8B6914;
    --bg:       #0a0a0f;
    --surface:  #111827;
    --surface2: #1f2937;
    --border:   #1f2937;
    --text:     #F9FAFB;
    --dim:      #9CA3AF;
    --radius:   12px;
}

/* ── Ocultar chrome de Streamlit ────────────────────────── */
#MainMenu, footer, header { display: none !important; }
[data-testid="stToolbar"]  { display: none !important; }
.stDeployButton            { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

/* ── App base ───────────────────────────────────────────── */
.stApp { background: var(--bg) !important; }
.block-container { padding-top: 2rem !important; padding-bottom: 3rem !important; }

/* ── Sidebar ────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* ── Radio nav en sidebar ───────────────────────────────── */
[data-testid="stSidebar"] .stRadio > label { display: none !important; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
[data-testid="stSidebar"] .stRadio label {
    display: flex !important;
    align-items: center;
    padding: 9px 12px !important;
    border-radius: 8px !important;
    cursor: pointer;
    transition: background 0.15s;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: var(--surface2) !important;
}
[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
    background: rgba(201,168,76,0.12) !important;
    border-left: 3px solid var(--gold) !important;
}
[data-testid="stSidebar"] .stRadio p {
    font-size: 14px !important;
    font-weight: 500 !important;
    color: var(--text) !important;
    margin: 0 !important;
}

/* ── Métricas ───────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-top: 3px solid var(--gold) !important;
    border-radius: var(--radius) !important;
    padding: 18px 20px !important;
}
[data-testid="stMetricLabel"] p {
    font-size: 10px !important;
    color: var(--dim) !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    font-weight: 700 !important;
}
[data-testid="stMetricValue"] {
    font-size: 26px !important;
    font-weight: 800 !important;
    color: var(--text) !important;
    letter-spacing: -0.5px !important;
}

/* ── Botones ────────────────────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    transition: all 0.15s !important;
}
.stButton > button[kind="primary"] {
    background: var(--gold) !important;
    color: #000 !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    background: #b8943e !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"],
.stButton > button:not([kind]) {
    background: var(--surface2) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
}
.stButton > button:not([kind]):hover {
    border-color: var(--gold) !important;
    color: var(--gold) !important;
}

/* ── Tabs ───────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--surface) !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 4px !important;
    border: 1px solid var(--border) !important;
    margin-bottom: 20px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--dim) !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    padding: 8px 18px !important;
    border: none !important;
    transition: all 0.15s !important;
}
.stTabs [aria-selected="true"] {
    background: var(--gold) !important;
    color: #000 !important;
}

/* ── Inputs ─────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text) !important;
    font-size: 14px !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: var(--gold) !important;
    box-shadow: 0 0 0 2px rgba(201,168,76,0.15) !important;
}
.stSelectbox > div > div {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text) !important;
}

/* Labels */
.stTextInput label, .stNumberInput label, .stSelectbox label,
.stTextArea label,  .stDateInput label,   .stSlider label {
    font-size: 10px !important;
    font-weight: 700 !important;
    color: var(--dim) !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}

/* ── Form ───────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 24px !important;
}

/* ── Expander ───────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: var(--text) !important;
}

/* ── Dataframe ──────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
}

/* ── Divider ────────────────────────────────────────────── */
hr {
    border-color: var(--border) !important;
    margin: 20px 0 !important;
}

/* ── Chat ───────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stChatInput"] > div {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: var(--text) !important;
}

/* ── Alerts ─────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: var(--radius) !important;
}

/* ── Slider ─────────────────────────────────────────────── */
[data-baseweb="slider"] [role="slider"] {
    background: var(--gold) !important;
    border-color: var(--gold) !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# HELPERS UI
# ─────────────────────────────────────────────────────────────

def page_header(title: str, subtitle: str = "") -> None:
    """Título de página con barra dorada lateral."""
    sub = (f'<p style="margin:5px 0 0;color:#9CA3AF;font-size:14px;'
           f'font-weight:400;">{subtitle}</p>') if subtitle else ""
    st.markdown(f"""
    <div style="display:flex;align-items:flex-start;gap:16px;
                margin-bottom:28px;padding-bottom:20px;
                border-bottom:1px solid #1f2937;">
        <div style="width:4px;min-height:48px;
                    background:linear-gradient(180deg,#C9A84C 0%,#8B6914 100%);
                    border-radius:4px;flex-shrink:0;margin-top:4px;"></div>
        <div>
            <h1 style="margin:0;font-size:28px;font-weight:800;
                       color:#F9FAFB;letter-spacing:-0.5px;
                       line-height:1.2;">{title}</h1>
            {sub}
        </div>
    </div>
    """, unsafe_allow_html=True)


def gold_card(label: str, value: str, note: str = "", empty: bool = False) -> None:
    """Tarjeta de métrica con borde dorado superior."""
    val_color = "#4B5563" if empty else "#F9FAFB"
    note_html = (f'<div style="font-size:11px;color:#C9A84C;'
                 f'margin-top:6px;">{note}</div>') if note else ""
    st.markdown(f"""
    <div style="background:#111827;border:1px solid #1f2937;
                border-top:3px solid #C9A84C;border-radius:12px;
                padding:18px 20px;">
        <div style="font-size:10px;color:#9CA3AF;text-transform:uppercase;
                    letter-spacing:1px;font-weight:700;
                    margin-bottom:8px;">{label}</div>
        <div style="font-size:28px;font-weight:800;letter-spacing:-0.5px;
                    color:{val_color};">{value}</div>
        {note_html}
    </div>
    """, unsafe_allow_html=True)


def section_label(text: str) -> None:
    """Etiqueta de sección en mayúsculas."""
    st.markdown(f"""
    <div style="font-size:11px;font-weight:700;color:#6B7280;
                text-transform:uppercase;letter-spacing:1.5px;
                margin:24px 0 12px;">{text}</div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────

profile = get_athlete_profile()

with st.sidebar:

    # Logo
    st.markdown("""
    <div style="padding:20px 16px 16px;border-bottom:1px solid #1f2937;
                margin-bottom:12px;">
        <div style="display:flex;align-items:baseline;gap:1px;line-height:1;">
            <span style="font-size:28px;font-weight:900;color:#C9A84C;
                         letter-spacing:-2px;">L</span>
            <span style="font-size:22px;font-weight:800;color:#F9FAFB;
                         letter-spacing:-1px;">iftLog</span>
        </div>
        <div style="font-size:9px;color:#4B5563;text-transform:uppercase;
                    letter-spacing:2px;margin-top:3px;">Halterofilia Olímpica</div>
    </div>
    """, unsafe_allow_html=True)

    # Atleta
    if profile.get("nombre"):
        nombre_display = profile["nombre"].strip().title()
        cat    = profile.get("categoria_peso", "—")
        genero = profile.get("genero", "")
        estado = profile.get("estado_entrenamiento", "Normal")

        badge = {
            "Normal":            ("#064E3B", "#6EE7B7", "✓"),
            "Retorno de lesión": ("#451A03", "#FCD34D", "⚠"),
            "Lesión activa":     ("#450A0A", "#FCA5A5", "🚨"),
        }.get(estado, ("#064E3B", "#6EE7B7", "✓"))

        st.markdown(f"""
        <div style="padding:4px 4px 16px;">
            <div style="font-size:16px;font-weight:700;
                        color:#F9FAFB;">{nombre_display}</div>
            <div style="font-size:12px;color:#6B7280;margin:2px 0 10px;">
                Cat. {cat} kg · {genero}
            </div>
            <span style="background:{badge[0]};color:{badge[1]};
                         font-size:10px;font-weight:700;padding:3px 10px;
                         border-radius:20px;text-transform:uppercase;
                         letter-spacing:0.5px;">{badge[2]} {estado}</span>
        </div>
        """, unsafe_allow_html=True)

    # Countdown competencia
    if profile.get("fecha_competencia"):
        try:
            delta   = datetime.strptime(profile["fecha_competencia"], "%Y-%m-%d") - datetime.today()
            semanas = max(0, delta.days // 7)
            dias    = max(0, delta.days % 7)
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#1a1400,#221900);
                        border:1px solid rgba(201,168,76,0.25);
                        border-left:3px solid #C9A84C;border-radius:10px;
                        padding:12px 14px;margin:0 0 12px;">
                <div style="font-size:9px;color:#C9A84C;text-transform:uppercase;
                            letter-spacing:1.5px;font-weight:700;">
                    Próxima competencia
                </div>
                <div style="font-size:22px;font-weight:800;color:#F9FAFB;margin:4px 0 1px;">
                    {semanas}
                    <span style="font-size:12px;color:#9CA3AF;font-weight:400;">
                        sem {dias}d
                    </span>
                </div>
                <div style="font-size:11px;color:#6B7280;">
                    {profile["fecha_competencia"]}
                </div>
            </div>
            """, unsafe_allow_html=True)
        except Exception:
            pass

    # Navegación
    page = st.radio(
        "Navegación",
        options=["Análisis", "Sesiones", "Perfil", "Herramientas", "Entrenador IA"],
        label_visibility="collapsed",
    )

    # Alerta perfil incompleto
    if not profile_is_complete():
        st.markdown("""
        <div style="background:#1c1400;border:1px solid rgba(201,168,76,0.3);
                    border-radius:8px;padding:10px 12px;margin-top:8px;">
            <div style="font-size:11px;color:#FCD34D;font-weight:600;">
                ⚠ Completa tu perfil para activar todas las funciones
            </div>
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# PÁGINA: ANÁLISIS
# ─────────────────────────────────────────────────────────────

if page == "Análisis":
    page_header("Análisis de Progresión", "Métricas y evolución de tu entrenamiento")

    current_1rms = get_current_1rms()
    ratio_data   = get_snatch_cj_ratio()
    tonnage_data = get_weekly_tonnage(weeks=8)
    vol_alert    = get_volume_trend_alert(lookback_weeks=4)

    # ── 1RM ──────────────────────────────────────────────────
    section_label("1RM Actuales")
    main_mvs = ["Snatch", "Clean & Jerk", "Front Squat", "Back Squat"]
    cols     = st.columns(4)

    for col, mv in zip(cols, main_mvs):
        with col:
            if mv in current_1rms:
                d    = current_1rms[mv]
                icon = "✅ Real" if d["source"] == "actual" else "📐 Estimado"
                gold_card(mv, f"{d['weight_kg']} kg", f"{icon} · {d['date']}")
            else:
                gold_card(mv, "—", "Sin datos", empty=True)

    st.markdown("<div style='margin:24px 0 0;'></div>", unsafe_allow_html=True)

    # ── Relación + Volumen ────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        section_label("Relación Snatch / C&J")

        if ratio_data["status"] == "unavailable":
            missing = " y ".join(ratio_data["missing"])
            st.warning(f"No calculable — falta 1RM de: **{missing}**")
            st.caption("Registra sesiones o ingresa 1RMs en Herramientas para activar esta métrica.")
        else:
            pct    = ratio_data["ratio_percent"]
            status = ratio_data["status"]

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct,
                number={"suffix": "%", "font": {"size": 40, "color": "#F9FAFB"}},
                gauge={
                    "axis": {
                        "range": [68, 96],
                        "ticksuffix": "%",
                        "tickcolor": "#6B7280",
                        "tickfont":  {"color": "#6B7280", "size": 11},
                    },
                    "bar":   {"color": "#C9A84C", "thickness": 0.28},
                    "bgcolor": "#111827",
                    "bordercolor": "#1f2937",
                    "steps": [
                        {"range": [68, 78], "color": "rgba(239,68,68,0.15)"},
                        {"range": [78, 84], "color": "rgba(16,185,129,0.15)"},
                        {"range": [84, 96], "color": "rgba(245,158,11,0.15)"},
                    ],
                    "threshold": {
                        "line":      {"color": "#C9A84C", "width": 3},
                        "thickness": 0.8,
                        "value":     pct,
                    },
                },
            ))
            fig_gauge.update_layout(
                height=230,
                margin=dict(t=20, b=0, l=20, r=20),
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#F9FAFB",
            )
            st.plotly_chart(fig_gauge, width="stretch")

            msgs = {
                "ok":   ("✅ Rango normal (78–84%)", "success"),
                "low":  ("⚠️ Bajo el rango — posible déficit en snatch", "warning"),
                "high": ("⚠️ Sobre el rango — revisar jerk / fuerza de empuje", "warning"),
            }
            msg, lvl = msgs.get(status, (status, "info"))
            getattr(st, lvl)(msg)

    with col_r:
        section_label("Alerta de Volumen Semanal")
        alert = vol_alert["alert_level"]

        alert_cfg = {
            "normal":        (st.success, f"✅ Volumen normal ({vol_alert['change_pct']:+.1f}%)"),
            "warning_drop":  (st.warning, f"⚠️ Caída: **{vol_alert['change_pct']:+.1f}%** — monitorear"),
            "critical_drop": (st.error,   f"🚨 Caída crítica: **{vol_alert['change_pct']:+.1f}%**"),
            "warning_spike": (st.warning, f"⚠️ Pico: **{vol_alert['change_pct']:+.1f}%** — riesgo sobrecarga"),
            "no_data":       (st.info,    "Sin suficientes datos para calcular tendencia"),
        }
        fn, msg = alert_cfg.get(alert, (st.info, alert))
        fn(msg)

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Esta semana",    f"{vol_alert['current_week_kg']:.0f} kg")
        with c2: st.metric("Promedio 4 sem", f"{vol_alert['avg_prev_weeks_kg']:.0f} kg")
        with c3: st.metric("Cambio",         f"{vol_alert['change_pct']:+.1f}%")

    st.divider()

    # ── Gráficos ──────────────────────────────────────────────
    if tonnage_data:
        df = pd.DataFrame(tonnage_data)

        section_label("Tonelaje por Movimiento")
        all_mvs     = sorted(df["movement_name"].unique().tolist())
        default_mvs = [m for m in ["Snatch", "Clean & Jerk", "Front Squat"] if m in all_mvs]

        sel = st.multiselect("Movimientos", options=all_mvs, default=default_mvs or all_mvs[:3])

        if sel:
            fig = px.line(
                df[df["movement_name"].isin(sel)],
                x="week", y="tonnage_kg", color="movement_name",
                markers=True,
                labels={"week": "Semana", "tonnage_kg": "Tonelaje (kg)", "movement_name": ""},
                color_discrete_sequence=["#C9A84C", "#60A5FA", "#34D399", "#F87171", "#A78BFA"],
            )
            fig.update_layout(
                height=360,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#F9FAFB",
                legend_title="",
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#6B7280"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#6B7280"),
            )
            st.plotly_chart(fig, width="stretch")

        # Barras total semanal
        df_t = (
            df.groupby("week")["tonnage_kg"]
            .sum().reset_index()
            .rename(columns={"tonnage_kg": "total"})
            .sort_values("week")
        )
        fig_bar = px.bar(
            df_t, x="week", y="total",
            labels={"week": "Semana", "total": "Tonelaje Total (kg)"},
            color_discrete_sequence=["#C9A84C"],
            title="Volumen total semanal",
        )
        fig_bar.update_traces(marker_opacity=0.85)
        fig_bar.update_layout(
            height=260,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#F9FAFB",
            showlegend=False,
            title_font_color="#9CA3AF",
            title_font_size=13,
            xaxis=dict(showgrid=False, color="#6B7280"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#6B7280"),
        )
        st.plotly_chart(fig_bar, width="stretch")

    else:
        st.markdown("""
        <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;
                    padding:40px;text-align:center;">
            <div style="font-size:32px;margin-bottom:12px;">📭</div>
            <div style="color:#9CA3AF;font-size:15px;font-weight:500;">
                Sin datos de entrenamiento aún
            </div>
            <div style="color:#6B7280;font-size:13px;margin-top:6px;">
                Registra tu primera sesión en <strong style="color:#C9A84C;">Sesiones</strong>
                o ingresa tus 1RM en <strong style="color:#C9A84C;">Herramientas</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# PÁGINA: SESIONES
# ─────────────────────────────────────────────────────────────

elif page == "Sesiones":
    page_header("Sesiones", "Registra y consulta tu historial de entrenamiento")

    tab_nueva, tab_historial = st.tabs(["➕  Registrar sesión", "📂  Historial"])

    with tab_nueva:
        if "new_session_sets" not in st.session_state:
            st.session_state.new_session_sets = []

        col_f, col_n = st.columns([1, 2])
        with col_f:
            session_date = st.date_input("Fecha", value=date.today(), format="YYYY-MM-DD")
        with col_n:
            session_notes = st.text_input("Notas (opcional)", placeholder="Ej: buena sesión, técnica sólida...")

        st.divider()

        movements  = get_all_movements()
        classics   = [m["name"] for m in movements if m["category"] == "classic"]
        variants   = [m["name"] for m in movements if m["category"] == "variant"]
        accessory  = [m["name"] for m in movements if m["category"] == "accessory"]
        mv_ordered = classics + variants + accessory

        col_mv, col_kg, col_ser, col_rep, col_rpe, col_btn = st.columns([3, 2, 1, 1, 1, 1])

        with col_mv:
            selected_mv = st.selectbox("Ejercicio", options=mv_ordered, key="set_movement")
        with col_kg:
            weight_kg = st.number_input("Peso (kg)", min_value=0.5, max_value=300.0, value=60.0, step=0.5, key="set_weight")
        with col_ser:
            series = st.number_input("Series", min_value=1, max_value=10, value=1, step=1, key="set_series")
        with col_rep:
            reps = st.number_input("Reps", min_value=1, max_value=10, value=3, step=1, key="set_reps")
        with col_rpe:
            rpe = st.number_input("RPE", min_value=6.0, max_value=10.0, value=8.0, step=0.5, key="set_rpe")
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("＋ Agregar", width="stretch", type="primary"):
                for _ in range(int(series)):
                    st.session_state.new_session_sets.append({
                        "movement":  selected_mv,
                        "weight_kg": weight_kg,
                        "reps":      reps,
                        "rpe":       rpe,
                        "set_order": len(st.session_state.new_session_sets) + 1,
                    })
                st.rerun()

        if st.session_state.new_session_sets:
            st.divider()
            section_label(f"{len(st.session_state.new_session_sets)} sets en esta sesión")

            current_1rms_local = get_current_1rms()

            for i, s in enumerate(st.session_state.new_session_sets):
                pct_str = "—"
                if s["movement"] in current_1rms_local:
                    pct     = (s["weight_kg"] / current_1rms_local[s["movement"]]["weight_kg"]) * 100
                    pct_str = f"{pct:.0f}%"

                c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 1, 1, 1, 1])
                with c1: st.write(f"**{s['set_order']}.** {s['movement']}")
                with c2: st.write(f"{s['weight_kg']} kg")
                with c3: st.write(f"×{s['reps']}")
                with c4: st.write(f"RPE {s['rpe']}")
                with c5: st.write(pct_str)
                with c6:
                    if st.button("✕", key=f"del_{i}"):
                        st.session_state.new_session_sets.pop(i)
                        for j, s_ in enumerate(st.session_state.new_session_sets):
                            s_["set_order"] = j + 1
                        st.rerun()

            st.divider()
            tonnage_s = sum(s["weight_kg"] * s["reps"] for s in st.session_state.new_session_sets)
            st.metric("Tonelaje de esta sesión", f"{tonnage_s:.0f} kg")

            cg, cl = st.columns(2)
            with cg:
                if st.button("💾 Guardar sesión", width="stretch", type="primary"):
                    sid = insert_session(
                        session_uuid=str(uuid.uuid4()),
                        session_date=session_date.strftime("%Y-%m-%d"),
                        notes=session_notes,
                        source="manual",
                    )
                    if sid:
                        for s in st.session_state.new_session_sets:
                            insert_set(
                                session_id=sid,
                                movement_name=s["movement"],
                                weight_kg=s["weight_kg"],
                                reps=s["reps"],
                                set_order=s["set_order"],
                                rpe=s["rpe"],
                            )
                        n = len(st.session_state.new_session_sets)
                        st.session_state.new_session_sets = []
                        st.success(f"✅ Sesión guardada — {n} sets · {tonnage_s:.0f} kg")
                        st.rerun()
            with cl:
                if st.button("🗑️ Limpiar", width="stretch"):
                    st.session_state.new_session_sets = []
                    st.rerun()
        else:
            st.markdown("""
            <div style="color:#6B7280;font-size:13px;padding:12px 0;">
                Agrega el primer set usando el formulario de arriba 👆
            </div>
            """, unsafe_allow_html=True)

    with tab_historial:
        sessions = get_recent_sessions(limit=30)

        if not sessions:
            st.info("📭 Sin sesiones registradas aún.")
        else:
            st.caption(f"{len(sessions)} sesiones · más reciente primero")
            current_1rms_local = get_current_1rms()

            for sess in sessions:
                n_sets  = len(sess["sets"])
                tonnage = sum(s["weight_kg"] * s["reps"] for s in sess["sets"])
                icon    = "📱" if sess.get("source") == "pwa" else "💻"
                header  = f"{icon} {sess['date']}  ·  {n_sets} sets  ·  {tonnage:.0f} kg"

                with st.expander(header):
                    if sess["notes"]:
                        st.caption(f"📝 {sess['notes']}")

                    if sess["sets"]:
                        df_s = pd.DataFrame(sess["sets"])
                        df_d = df_s[["set_order", "movement", "weight_kg", "reps", "rpe"]].copy()
                        df_d.columns = ["#", "Ejercicio", "Peso (kg)", "Reps", "RPE"]
                        df_d["#"]   = range(1, len(df_d) + 1)

                        def calc_pct(row):
                            mv = row["Ejercicio"]
                            if mv in current_1rms_local:
                                return f"{(row['Peso (kg)'] / current_1rms_local[mv]['weight_kg'] * 100):.0f}%"
                            return "—"

                        df_d["% 1RM"] = df_d.apply(calc_pct, axis=1)

                        ct, cm = st.columns([3, 1])
                        with ct: st.dataframe(df_d, width="stretch", hide_index=True)
                        with cm:
                                st.metric("Tonelaje", f"{tonnage:.0f} kg")
                                st.metric("Sets", n_sets)
                                st.markdown("<br>", unsafe_allow_html=True)
                                if st.button(
                                    "🗑️ Borrar",
                                    key=f"del_sess_{sess['id']}",
                                    width="stretch",
                                ):
                                    delete_session(sess["id"])
                                    st.rerun()

# ─────────────────────────────────────────────────────────────
# PÁGINA: PERFIL
# ─────────────────────────────────────────────────────────────

elif page == "Perfil":
    page_header("Perfil del Atleta", "El entrenador IA usa estos datos para personalizar cada recomendación")

    profile = get_athlete_profile()

    with st.form("athlete_profile_form"):
        st.subheader("Datos personales")
        c1, c2, c3 = st.columns(3)

        with c1:
            nombre = st.text_input("Nombre", value=profile.get("nombre", ""), placeholder="Tu nombre")
        with c2:
            edad = st.number_input("Edad", min_value=14, max_value=60,
                                   value=int(profile["edad"]) if profile.get("edad") else 20, step=1)
        with c3:
            genero = st.selectbox("Género", options=["Masculino", "Femenino"],
                                  index=0 if profile.get("genero", "Masculino") == "Masculino" else 1)

        st.divider()
        st.subheader("Datos deportivos")
        c4, c5, c6 = st.columns(3)

        with c4:
            cats       = WEIGHT_CATEGORIES.get(genero, WEIGHT_CATEGORIES["Masculino"])
            cur_cat    = profile.get("categoria_peso", "")
            cat_idx    = cats.index(cur_cat) if cur_cat in cats else 0
            categoria_peso = st.selectbox("Categoría de peso (kg)", options=cats, index=cat_idx)

        with c5:
            años_experiencia = st.number_input("Años en halterofilia", min_value=0, max_value=30,
                                               value=int(profile.get("años_experiencia", 0)), step=1)

        with c6:
            niv_idx = COMPETITION_LEVELS.index(profile["nivel_competitivo"]) \
                      if profile.get("nivel_competitivo") in COMPETITION_LEVELS else 1
            nivel_competitivo = st.selectbox("Nivel competitivo", options=COMPETITION_LEVELS, index=niv_idx)

        c7, c8 = st.columns(2)
        with c7:
            federacion = st.text_input("Federación", value=profile.get("federacion", ""),
                                       placeholder="Ej: Federación Chilena de Halterofilia")
        with c8:
            fecha_actual = None
            if profile.get("fecha_competencia"):
                try:
                    fecha_actual = datetime.strptime(profile["fecha_competencia"], "%Y-%m-%d").date()
                except Exception:
                    pass
            fecha_competencia = st.date_input("Próxima competencia (opcional)",
                                              value=fecha_actual, min_value=date.today(), format="YYYY-MM-DD")

        st.divider()
        st.subheader("Estado de entrenamiento")

        est_idx = TRAINING_STATES.index(profile["estado_entrenamiento"]) \
                  if profile.get("estado_entrenamiento") in TRAINING_STATES else 0
        estado_entrenamiento = st.selectbox(
            "Estado actual", options=TRAINING_STATES, index=est_idx,
            help="El entrenador IA adapta todas sus recomendaciones según este estado.",
        )

        notas_adicionales = st.text_area(
            "Notas para el entrenador (opcional)",
            value=profile.get("notas_adicionales", ""),
            placeholder="Ej: dolor crónico en rodilla derecha, preferencia por entrenar mañanas...",
            height=80,
        )

        if st.form_submit_button("💾 Guardar perfil", width="stretch", type="primary"):
            save_athlete_profile(
                nombre               = nombre,
                edad                 = int(edad),
                genero               = genero,
                categoria_peso       = categoria_peso,
                años_experiencia     = int(años_experiencia),
                federacion           = federacion,
                nivel_competitivo    = nivel_competitivo,
                fecha_competencia    = fecha_competencia.strftime("%Y-%m-%d") if fecha_competencia else None,
                estado_entrenamiento = estado_entrenamiento,
                notas_adicionales    = notas_adicionales,
            )
            st.success("✅ Perfil guardado correctamente.")
            st.rerun()


# ─────────────────────────────────────────────────────────────
# PÁGINA: HERRAMIENTAS
# ─────────────────────────────────────────────────────────────

elif page == "Herramientas":
    page_header("Herramientas", "Calculadoras y registro de máximos")

    tab_prilepin, tab_brzycki, tab_1rm = st.tabs([
        "📊  Calculadora Prilepin",
        "🔢  Estimador 1RM",
        "🏆  Registro 1RM",
    ])

    with tab_prilepin:
        st.subheader("Calculadora de Zonas Prilepin")
        st.caption("Calcula el rango de trabajo óptimo según tus 1RM actuales.")

        current_1rms = get_current_1rms()
        c1, c2 = st.columns(2)
        with c1:
            mv_opts    = list(current_1rms.keys()) if current_1rms else ["Snatch"]
            p_mv       = st.selectbox("Movimiento", options=mv_opts)
        with c2:
            intensity  = st.slider("Intensidad (%1RM)", min_value=60, max_value=100, value=80, step=1)

        if p_mv in current_1rms:
            one_rm = current_1rms[p_mv]["weight_kg"]
            w_abs  = round(one_rm * intensity / 100, 1)

            if intensity >= 90:
                zona, reps_opt, reps_max, reps_ser = "Máxima (90%+)", "7-10", 14, "1-2"
            elif intensity >= 80:
                zona, reps_opt, reps_max, reps_ser = "Alta (80-89%)", "15-20", 24, "2-4"
            elif intensity >= 70:
                zona, reps_opt, reps_max, reps_ser = "Moderada (70-79%)", "18-24", 30, "3-6"
            else:
                zona, reps_opt, reps_max, reps_ser = "Técnica (<70%)", "Libre", None, "3-6"

            st.divider()
            cc1, cc2, cc3, cc4 = st.columns(4)
            with cc1: st.metric("Peso de trabajo",      f"{w_abs} kg")
            with cc2: st.metric("Zona",                 zona)
            with cc3: st.metric("Reps óptimas totales", reps_opt)
            with cc4: st.metric("Reps por serie",        reps_ser)

            if reps_max:
                st.caption(f"⚠️ Límite absoluto: **{reps_max} reps totales** en esta zona (Prilepin).")

            st.divider()
            st.subheader("Distribución sugerida")
            reps_map = {"1-2": [1, 2], "2-4": [2, 3], "3-6": [3, 4, 5]}
            sugs     = []
            for r in reps_map.get(reps_ser, [3]):
                if reps_max:
                    opt_s = int(reps_opt.split("-")[1]) // r if "-" in reps_opt else reps_max // r
                    sugs.append({
                        "Reps/serie": r, "Series óptimas": opt_s,
                        "Series máximas": reps_max // r, "Peso (kg)": w_abs,
                        "Tonelaje óptimo": f"{opt_s * r * w_abs:.0f} kg",
                    })
            if sugs:
                st.dataframe(pd.DataFrame(sugs), width="stretch", hide_index=True)
        else:
            st.info(f"No hay 1RM registrado para **{p_mv}**. Regístralo en la pestaña **Registro 1RM**.")

    with tab_brzycki:
        st.subheader("Estimador de 1RM — Brzycki")
        st.caption("Estima tu 1RM a partir de un set submáximo (válido para 1-5 reps).")

        b1, b2 = st.columns(2)
        with b1: bw = st.number_input("Peso levantado (kg)", min_value=1.0, max_value=300.0, value=80.0, step=0.5)
        with b2: br = st.number_input("Repeticiones", min_value=1, max_value=5, value=3, step=1)

        est = bw if br == 1 else bw * 36 / (37 - br)
        if br == 1:
            st.info("Para 1 repetición, el peso levantado ES el 1RM directamente.")
        st.metric("1RM Estimado", f"{est:.2f} kg")

        st.divider()
        st.caption("Tabla de porcentajes:")
        st.dataframe(pd.DataFrame({
            "% 1RM":     [f"{p}%" for p in [100, 95, 90, 85, 80, 75, 70]],
            "Peso (kg)": [round(est * p / 100, 1) for p in [100, 95, 90, 85, 80, 75, 70]],
        }), width="stretch", hide_index=True)

    with tab_1rm:
        st.subheader("Registro Manual de 1RM")
        st.caption("Ingresa tus 1RM actuales o históricos para que el sistema y el entrenador los usen.")

        with st.form("form_1rm_manual"):
            m1, m2, m3 = st.columns([3, 2, 2])
            with m1:
                mv_names = [m["name"] for m in get_all_movements()]
                mv_1rm   = st.selectbox("Movimiento", options=mv_names)
            with m2:
                w_1rm = st.number_input("Peso (kg)", min_value=1.0, max_value=400.0, value=80.0, step=0.5)
            with m3:
                f_1rm = st.date_input("Fecha", value=date.today(), format="YYYY-MM-DD")

            if st.form_submit_button("💾 Guardar 1RM", width="stretch", type="primary"):
                save_manual_1rm(mv_1rm, float(w_1rm), f_1rm.strftime("%Y-%m-%d"))
                st.success(f"✅ 1RM guardado: {mv_1rm} → {w_1rm} kg ({f_1rm})")
                st.rerun()

        st.divider()
        st.subheader("1RM Registrados")
        c1rms = get_current_1rms()

        if not c1rms:
            st.info("Sin 1RM registrados. Usa el formulario de arriba para ingresar tus máximos.")
        else:
            st.dataframe(pd.DataFrame([{
                "Movimiento": mv, "1RM (kg)": d["weight_kg"],
                "Fecha": d["date"],
                "Fuente": "✅ Real" if d["source"] == "actual" else "📐 Estimado",
            } for mv, d in c1rms.items()]), width="stretch", hide_index=True)

        st.divider()
        st.subheader("Progresión Histórica de 1RM")

        if c1rms:
            mv_h = st.selectbox("Ver progresión de:", options=list(c1rms.keys()))
            hist = get_1rm_history_by_movement(mv_h)

            if len(hist) > 1:
                fig_h = px.line(
                    pd.DataFrame(hist), x="date", y="weight_kg",
                    markers=True,
                    title=f"Progresión 1RM — {mv_h}",
                    labels={"date": "Fecha", "weight_kg": "1RM (kg)"},
                    color_discrete_sequence=["#C9A84C"],
                )
                fig_h.update_layout(
                    height=280,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#F9FAFB",
                    showlegend=False,
                    title_font_color="#9CA3AF",
                    title_font_size=13,
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#6B7280"),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#6B7280"),
                )
                st.plotly_chart(fig_h, width="stretch")
            elif len(hist) == 1:
                st.info("Solo hay un registro. Se necesitan al menos 2 puntos para mostrar la curva.")

        st.divider()
        with st.expander("⚠️ Borrar registros de 1RM"):
            st.caption("Elimina TODOS los registros de 1RM para el movimiento. No se puede deshacer.")
            mv_all = [m["name"] for m in get_all_movements()]
            cd, cb = st.columns([3, 1])
            with cd:
                mv_del = st.selectbox("Movimiento", options=mv_all, key="del_1rm_mv")
            with cb:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Borrar", key="btn_del_1rm", width="stretch"):
                    delete_1rm(mv_del)
                    st.warning(f"1RM de {mv_del} eliminado.")
                    st.rerun()


# ─────────────────────────────────────────────────────────────
# PÁGINA: ENTRENADOR IA
# ─────────────────────────────────────────────────────────────

elif page == "Entrenador IA":
    page_header("Entrenador IA", "Powered by Claude · Razona sobre tus datos reales")

    if not profile_is_complete():
        st.warning("⚠️ Completa tu **Perfil** antes de usar el entrenador para obtener recomendaciones precisas.")

    if "chat_messages" not in st.session_state:
        history = get_coach_history(last_n=20)
        st.session_state.chat_messages = history if history else []
    if "show_all_messages" not in st.session_state:
        st.session_state.show_all_messages = False

    col_ctx, col_clr = st.columns([5, 1])
    with col_ctx:
        with st.expander("👁️ Ver contexto actual del entrenador"):
            try:
                st.code(build_athlete_context(), language=None)
            except Exception as e:
                st.error(f"Error: {e}")
    with col_clr:
        if st.button("🗑️ Limpiar", width="stretch"):
            st.session_state.chat_messages = []
            st.rerun()

    section_label("Sugerencias rápidas")
    sq_cols = st.columns(3)
    for i, (col, q) in enumerate(zip(sq_cols, [
        "¿Qué sesión me recomiendas para mañana?",
        "Analiza mi progresión de las últimas semanas",
        "¿Qué modelo de periodización me sugerirías?",
    ])):
        with col:
            if st.button(q, key=f"sq_{i}", width="stretch"):
                st.session_state["_pending_q"] = q

    st.divider()

    # Mostrar solo los últimos 10 mensajes por defecto
    all_msgs = st.session_state.chat_messages
    if len(all_msgs) > 10 and not st.session_state.show_all_messages:
        msgs_to_show = all_msgs[-10:]
        if st.button(f"Ver {len(all_msgs) - 10} mensajes anteriores", use_container_width=False):
            st.session_state.show_all_messages = True
            st.rerun()
    else:
        msgs_to_show = all_msgs

    for msg in msgs_to_show:
        with st.chat_message(msg["role"], avatar="🏋️" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    pending   = st.session_state.pop("_pending_q", None)
    user_in   = st.chat_input("Escribe tu pregunta al entrenador...")
    question  = pending or user_in

    if question:
        with st.chat_message("user", avatar="👤"):
            st.markdown(question)
        st.session_state.chat_messages.append({"role": "user", "content": question})

        with st.chat_message("assistant", avatar="🏋️"):
            with st.spinner("Analizando tus datos..."):
                response = ask_coach(question)
            st.markdown(response)
        st.session_state.chat_messages.append({"role": "assistant", "content": response})
        st.rerun()