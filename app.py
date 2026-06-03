"""
app.py — LiftLog Dashboard
==========================
Dashboard principal con tres secciones:
  · Análisis:   métricas, gráficos de progresión, alertas
  · Entrenador: chat con el coach IA basado en Claude API
  · Sesiones:   registro histórico importado desde PWA

Correr con: streamlit run app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Agregar src/ al path para imports locales
sys.path.insert(0, str(Path(__file__).parent / "src"))

from coach import ask_coach
from db import (
    get_current_1rms,
    get_recent_sessions,
    get_snatch_cj_ratio,
    get_volume_trend_alert,
    get_weekly_tonnage,
    initialize_db,
)

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="LiftLog",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialize_db()  # Idempotente: crea tablas solo si no existen

# ─────────────────────────────────────────────────────────────
# ESTILOS
# ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; }
.stDataFrame td  { font-family: 'SF Mono', monospace; font-size: 13px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# SIDEBAR — NAVEGACIÓN
# ─────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🏋️ LiftLog")
    st.caption("Halterofilia Olímpica")
    st.divider()

    page = st.radio(
        "Navegar",
        options=["📊 Análisis", "🤖 Entrenador", "📋 Sesiones"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("⚠️ Retorno de lesión: <4 sem")
    st.caption("Frecuencia: 5-6 días/semana")
    st.caption("Sin periodización formal activa")


# ─────────────────────────────────────────────────────────────
# PÁGINA: ANÁLISIS
# ─────────────────────────────────────────────────────────────

if page == "📊 Análisis":
    st.title("📊 Análisis de Progresión")

    current_1rms = get_current_1rms()
    ratio_data   = get_snatch_cj_ratio()
    tonnage_data = get_weekly_tonnage(weeks=8)
    vol_alert    = get_volume_trend_alert(lookback_weeks=4)

    # ── Sección 1: 1RM principales ───────────────────────────
    st.subheader("1RM Actuales")

    main_movements = ["Snatch", "Clean & Jerk", "Front Squat", "Back Squat"]
    cols = st.columns(4)

    for col, mv in zip(cols, main_movements):
        with col:
            if mv in current_1rms:
                d    = current_1rms[mv]
                icon = "✅" if d["source"] == "actual" else "📐"
                st.metric(
                    label=mv,
                    value=f"{d['weight_kg']} kg",
                    help=f"{icon} {d['source'].capitalize()} · {d['date']}",
                )
            else:
                st.metric(label=mv, value="—", help="Sin datos registrados")

    st.divider()

    # ── Sección 2: Relación Snatch/C&J + Alerta de volumen ──
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Relación Snatch / C&J")

        if ratio_data["status"] == "unavailable":
            missing = " y ".join(ratio_data["missing"])
            st.warning(f"No calculable — falta 1RM de: **{missing}**")
            st.caption("Registra los movimientos clásicos para activar esta métrica.")
        else:
            pct    = ratio_data["ratio_percent"]
            status = ratio_data["status"]

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct,
                number={"suffix": "%", "font": {"size": 36}},
                gauge={
                    "axis": {"range": [68, 96], "ticksuffix": "%"},
                    "bar":  {"color": "#2196F3", "thickness": 0.3},
                    "steps": [
                        {"range": [68, 78], "color": "rgba(255,80,80,0.3)"},
                        {"range": [78, 84], "color": "rgba(80,200,80,0.3)"},
                        {"range": [84, 96], "color": "rgba(255,180,0,0.3)"},
                    ],
                    "threshold": {
                        "line":      {"color": "white", "width": 3},
                        "thickness": 0.8,
                        "value":     pct,
                    },
                },
            ))
            fig_gauge.update_layout(
                height=220,
                margin=dict(t=20, b=0, l=20, r=20),
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#fafafa",
            )
            st.plotly_chart(fig_gauge, use_container_width=True)

            msgs = {
                "ok":   ("✅ Rango normal (78–84%)", "success"),
                "low":  ("⚠️ Por debajo del rango — posible déficit en snatch", "warning"),
                "high": ("⚠️ Por encima del rango — revisar jerk / fuerza de empuje", "warning"),
            }
            msg, level = msgs.get(status, (status, "info"))
            getattr(st, level)(msg)

    with col_right:
        st.subheader("Alerta de Volumen Semanal")

        alert = vol_alert["alert_level"]

        alert_config = {
            "normal":        (st.success, f"✅ Volumen normal ({vol_alert['change_pct']:+.1f}%)"),
            "warning_drop":  (st.warning, f"⚠️ Caída de volumen: **{vol_alert['change_pct']:+.1f}%** — monitorear fatiga"),
            "critical_drop": (st.error,   f"🚨 Caída crítica: **{vol_alert['change_pct']:+.1f}%** — revisar lesión/sobreentrenamiento"),
            "warning_spike": (st.warning, f"⚠️ Pico de volumen: **{vol_alert['change_pct']:+.1f}%** — riesgo de carga excesiva"),
            "no_data":       (st.info,    "Sin suficientes datos para calcular tendencia"),
        }

        func, msg = alert_config.get(alert, (st.info, alert))
        func(msg)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Esta semana",    f"{vol_alert['current_week_kg']:.0f} kg")
        with c2:
            st.metric("Promedio 4 sem", f"{vol_alert['avg_prev_weeks_kg']:.0f} kg")
        with c3:
            st.metric("Cambio",         f"{vol_alert['change_pct']:+.1f}%")

    st.divider()

    # ── Sección 3: Gráficos de tonelaje ─────────────────────
    if tonnage_data:
        df = pd.DataFrame(tonnage_data)

        st.subheader("Tonelaje por Movimiento")

        all_mvs     = sorted(df["movement_name"].unique().tolist())
        default_mvs = [m for m in ["Snatch", "Clean & Jerk", "Front Squat"] if m in all_mvs]

        selected_mvs = st.multiselect(
            "Movimientos",
            options=all_mvs,
            default=default_mvs or all_mvs[:3],
        )

        if selected_mvs:
            df_filt = df[df["movement_name"].isin(selected_mvs)]

            fig_lines = px.line(
                df_filt,
                x="week", y="tonnage_kg", color="movement_name",
                markers=True,
                labels={
                    "week":          "Semana",
                    "tonnage_kg":    "Tonelaje (kg × reps)",
                    "movement_name": "",
                },
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_lines.update_layout(
                height=380,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#fafafa",
                legend_title="",
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            )
            st.plotly_chart(fig_lines, use_container_width=True)

        # Tonelaje total semanal (barras)
        df_total = (
            df.groupby("week")["tonnage_kg"]
            .sum()
            .reset_index()
            .rename(columns={"tonnage_kg": "total"})
            .sort_values("week")
        )

        fig_bar = px.bar(
            df_total,
            x="week", y="total",
            labels={"week": "Semana", "total": "Tonelaje Total (kg)"},
            color_discrete_sequence=["#1976D2"],
            title="Volumen total semanal",
        )
        fig_bar.update_layout(
            height=280,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#fafafa",
            showlegend=False,
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    else:
        st.info("📭 Sin datos de entrenamiento aún — importa sesiones desde la PWA.")


# ─────────────────────────────────────────────────────────────
# PÁGINA: ENTRENADOR
# ─────────────────────────────────────────────────────────────

elif page == "🤖 Entrenador":
    st.title("🤖 Entrenador Inteligente")
    st.caption("Razona sobre tus datos reales de entrenamiento · Powered by Claude")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # ── Controles ──────────────────────────────────────────
    col_ctrl1, col_ctrl2 = st.columns([6, 1])
    with col_ctrl2:
        if st.button("🗑️ Limpiar", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()

    # ── Preguntas sugeridas ────────────────────────────────
    st.caption("Sugerencias rápidas:")
    sq_cols = st.columns(3)
    quick_qs = [
        "¿Qué sesión me recomiendas para mañana?",
        "Analiza mi progresión de las últimas semanas",
        "¿Qué modelo de periodización me sugerirías ahora?",
    ]
    for i, (col, q) in enumerate(zip(sq_cols, quick_qs)):
        with col:
            if st.button(q, key=f"sq_{i}", use_container_width=True):
                st.session_state["_pending_q"] = q

    st.divider()

    # ── Mostrar historial del chat ─────────────────────────
    for msg in st.session_state.chat_messages:
        avatar = "🏋️" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # ── Procesar input ────────────────────────────────────
    pending_q  = st.session_state.pop("_pending_q", None)
    user_input = st.chat_input("Escribe tu pregunta al entrenador...")
    question   = pending_q or user_input

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


# ─────────────────────────────────────────────────────────────
# PÁGINA: SESIONES
# ─────────────────────────────────────────────────────────────

elif page == "📋 Sesiones":
    st.title("📋 Sesiones Registradas")

    sessions = get_recent_sessions(limit=30)

    if not sessions:
        st.info("📭 Sin sesiones importadas aún.")
        st.caption("Las sesiones se importan automáticamente cuando terminas un entrenamiento en la PWA y guardas el JSON en iCloud Drive.")
        st.caption("Para importar manualmente: `python src/sync.py --backfill`")
    else:
        st.caption(f"{len(sessions)} sesiones · más reciente primero")

        # Una sola query antes del loop
        current_1rms_local = get_current_1rms()

        for sess in sessions:
            n_sets  = len(sess["sets"])
            tonnage = sum(s["weight_kg"] * s["reps"] for s in sess["sets"])
            header  = f"📅 {sess['date']}  ·  {n_sets} sets  ·  {tonnage:.0f} kg tonelaje"

            with st.expander(header):
                if sess["notes"]:
                    st.caption(f"📝 {sess['notes']}")

                if sess["sets"]:
                    df_sets = pd.DataFrame(sess["sets"])

                    df_display = df_sets[["set_order", "movement", "weight_kg", "reps"]].copy()
                    df_display.columns = ["#", "Ejercicio", "Peso (kg)", "Reps"]
                    df_display["#"] = range(1, len(df_display) + 1)

                    def calc_pct(row):
                        mv = row["Ejercicio"]
                        if mv in current_1rms_local:
                            pct = (row["Peso (kg)"] / current_1rms_local[mv]["weight_kg"]) * 100
                            return f"{pct:.0f}%"
                        return "—"

                    df_display["% 1RM"] = df_display.apply(calc_pct, axis=1)

                    col_t, col_m = st.columns([3, 1])
                    with col_t:
                        st.dataframe(
                            df_display,
                            use_container_width=True,
                            hide_index=True,
                        )
                    with col_m:
                        st.metric("Tonelaje", f"{tonnage:.0f} kg")
                        st.metric("Sets",     n_sets)
                        st.caption(f"Origen: {sess.get('source', 'pwa')}")