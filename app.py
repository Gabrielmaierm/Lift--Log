"""
app.py — LiftLog Dashboard
==========================
Dashboard principal con cinco secciones:
  · Análisis:     métricas, gráficos de progresión, alertas
  · Sesiones:     registro histórico + entrada manual
  · Perfil:       datos del atleta, editables desde la interfaz
  · Herramientas: calculadora Prilepin + estimador 1RM + registro 1RM
  · Entrenador:   chat con el coach IA (plus)

Correr con: streamlit run app.py
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
    get_1rm_history_by_movement,
    get_all_movements,
    get_athlete_profile,
    get_current_1rms,
    get_recent_sessions,
    get_snatch_cj_ratio,
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
# ESTILOS
# ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
.stDataFrame td  { font-family: 'SF Mono', monospace; font-size: 13px; }
[data-testid="metric-container"] {
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 10px;
    padding: 12px 16px;
}
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    margin-top: 4px;
}
.status-normal   { background: #1b5e20; color: #a5d6a7; }
.status-retorno  { background: #4a3500; color: #ffe082; }
.status-lesion   { background: #4a0000; color: #ef9a9a; }
.stSelectbox label, .stNumberInput label, .stTextInput label {
    font-size: 12px;
    font-weight: 600;
    color: #aaa;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────

profile = get_athlete_profile()

with st.sidebar:
    st.title("🏋️ LiftLog")

    if profile.get("nombre"):
        st.markdown(f"**{profile['nombre'].strip()}**")
        if profile.get("categoria_peso"):
            st.caption(f"Categoría {profile['categoria_peso']} kg · {profile.get('genero', '')}")
    else:
        st.caption("Halterofilia Olímpica")

    # Badge de estado
    estado = profile.get("estado_entrenamiento", "Normal")
    if estado == "Normal":
        st.markdown('<span class="status-badge status-normal">✓ Entrenamiento normal</span>',
                    unsafe_allow_html=True)
    elif estado == "Retorno de lesión":
        st.markdown('<span class="status-badge status-retorno">⚠ Retorno de lesión</span>',
                    unsafe_allow_html=True)
    elif estado == "Lesión activa":
        st.markdown('<span class="status-badge status-lesion">🚨 Lesión activa</span>',
                    unsafe_allow_html=True)

    st.divider()

    page = st.radio(
        "Navegar",
        options=[
            "📊 Análisis",
            "📋 Sesiones",
            "🏋️ Perfil",
            "📐 Herramientas",
            "🤖 Entrenador IA",
        ],
        label_visibility="collapsed",
    )

    if not profile_is_complete():
        st.divider()
        st.warning("⚠️ Completa tu perfil para activar todas las funciones.")

    if profile.get("fecha_competencia"):
        try:
            delta   = datetime.strptime(profile["fecha_competencia"], "%Y-%m-%d") - datetime.today()
            semanas = max(0, delta.days // 7)
            st.divider()
            st.caption(f"🏆 Competencia en **{semanas} semanas**")
            st.caption(profile["fecha_competencia"])
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# PÁGINA: PERFIL
# ─────────────────────────────────────────────────────────────

if page == "🏋️ Perfil":
    st.title("🏋️ Perfil del Atleta")
    st.caption("Estos datos son usados por el entrenador IA para personalizar todas las recomendaciones.")

    profile = get_athlete_profile()

    with st.form("athlete_profile_form"):
        st.subheader("Datos personales")
        col1, col2, col3 = st.columns(3)

        with col1:
            nombre = st.text_input(
                "Nombre",
                value=profile.get("nombre", ""),
                placeholder="Tu nombre",
            )
        with col2:
            edad = st.number_input(
                "Edad",
                min_value=14, max_value=60,
                value=int(profile["edad"]) if profile.get("edad") else 20,
                step=1,
            )
        with col3:
            genero = st.selectbox(
                "Género",
                options=["Masculino", "Femenino"],
                index=0 if profile.get("genero", "Masculino") == "Masculino" else 1,
            )

        st.divider()
        st.subheader("Datos deportivos")
        col4, col5, col6 = st.columns(3)

        with col4:
            cats        = WEIGHT_CATEGORIES.get(genero, WEIGHT_CATEGORIES["Masculino"])
            current_cat = profile.get("categoria_peso", "")
            cat_index   = cats.index(current_cat) if current_cat in cats else 0

            categoria_peso = st.selectbox(
                "Categoría de peso (kg)",
                options=cats,
                index=cat_index,
            )

        with col5:
            años_experiencia = st.number_input(
                "Años en halterofilia",
                min_value=0, max_value=30,
                value=int(profile.get("años_experiencia", 0)),
                step=1,
            )

        with col6:
            nivel_idx = COMPETITION_LEVELS.index(profile["nivel_competitivo"]) \
                        if profile.get("nivel_competitivo") in COMPETITION_LEVELS else 1

            nivel_competitivo = st.selectbox(
                "Nivel competitivo",
                options=COMPETITION_LEVELS,
                index=nivel_idx,
            )

        col7, col8 = st.columns(2)

        with col7:
            federacion = st.text_input(
                "Federación",
                value=profile.get("federacion", ""),
                placeholder="Ej: Federación Chilena de Halterofilia",
            )

        with col8:
            fecha_actual = None
            if profile.get("fecha_competencia"):
                try:
                    fecha_actual = datetime.strptime(
                        profile["fecha_competencia"], "%Y-%m-%d"
                    ).date()
                except Exception:
                    fecha_actual = None

            fecha_competencia = st.date_input(
                "Próxima competencia (opcional)",
                value=fecha_actual,
                min_value=date.today(),
                format="YYYY-MM-DD",
            )

        st.divider()
        st.subheader("Estado de entrenamiento")

        estado_idx = TRAINING_STATES.index(profile["estado_entrenamiento"]) \
                     if profile.get("estado_entrenamiento") in TRAINING_STATES else 0

        estado_entrenamiento = st.selectbox(
            "Estado actual",
            options=TRAINING_STATES,
            index=estado_idx,
            help="El entrenador IA adapta todas sus recomendaciones según este estado.",
        )

        notas_adicionales = st.text_area(
            "Notas adicionales para el entrenador (opcional)",
            value=profile.get("notas_adicionales", ""),
            placeholder="Ej: dolor crónico en rodilla derecha, preferencia por entrenar mañanas...",
            height=80,
        )

        submitted = st.form_submit_button(
            "💾 Guardar perfil",
            use_container_width=True,
            type="primary",
        )

        if submitted:
            fecha_str = fecha_competencia.strftime("%Y-%m-%d") \
                        if fecha_competencia else None

            save_athlete_profile(
                nombre               = nombre,
                edad                 = int(edad),
                genero               = genero,
                categoria_peso       = categoria_peso,
                años_experiencia     = int(años_experiencia),
                federacion           = federacion,
                nivel_competitivo    = nivel_competitivo,
                fecha_competencia    = fecha_str,
                estado_entrenamiento = estado_entrenamiento,
                notas_adicionales    = notas_adicionales,
            )
            st.success("✅ Perfil guardado correctamente.")
            st.rerun()


# ─────────────────────────────────────────────────────────────
# PÁGINA: ANÁLISIS
# ─────────────────────────────────────────────────────────────

elif page == "📊 Análisis":
    st.title("📊 Análisis de Progresión")

    if not profile_is_complete():
        st.info("💡 Completa tu **Perfil** para activar las recomendaciones personalizadas.")

    current_1rms = get_current_1rms()
    ratio_data   = get_snatch_cj_ratio()
    tonnage_data = get_weekly_tonnage(weeks=8)
    vol_alert    = get_volume_trend_alert(lookback_weeks=4)

    # ── 1RM principales ──────────────────────────────────────
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

    # ── Relación Snatch/C&J + Alerta volumen ─────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Relación Snatch / C&J")

        if ratio_data["status"] == "unavailable":
            missing = " y ".join(ratio_data["missing"])
            st.warning(f"No calculable — falta 1RM de: **{missing}**")
            st.caption("Registra sesiones con estos movimientos para activar la métrica.")
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
                        {"range": [68, 78], "color": "rgba(255,80,80,0.25)"},
                        {"range": [78, 84], "color": "rgba(80,200,80,0.25)"},
                        {"range": [84, 96], "color": "rgba(255,200,0,0.25)"},
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
            "warning_drop":  (st.warning, f"⚠️ Caída: **{vol_alert['change_pct']:+.1f}%** — monitorear fatiga"),
            "critical_drop": (st.error,   f"🚨 Caída crítica: **{vol_alert['change_pct']:+.1f}%** — revisar"),
            "warning_spike": (st.warning, f"⚠️ Pico: **{vol_alert['change_pct']:+.1f}%** — riesgo de sobrecarga"),
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

    # ── Gráficos de tonelaje ──────────────────────────────────
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
            df_filt   = df[df["movement_name"].isin(selected_mvs)]
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

        df_total = (
            df.groupby("week")["tonnage_kg"]
            .sum().reset_index()
            .rename(columns={"tonnage_kg": "total"})
            .sort_values("week")
        )
        fig_bar = px.bar(
            df_total, x="week", y="total",
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
        st.info("📭 Sin datos de entrenamiento aún. Registra tu primera sesión en **Sesiones**.")


# ─────────────────────────────────────────────────────────────
# PÁGINA: SESIONES
# ─────────────────────────────────────────────────────────────

elif page == "📋 Sesiones":
    st.title("📋 Sesiones")

    tab_nueva, tab_historial = st.tabs(["➕ Registrar sesión", "📂 Historial"])

    with tab_nueva:
        st.subheader("Nueva sesión")
        st.caption("Ingresa los sets de tu entrenamiento de hoy.")

        if "new_session_sets" not in st.session_state:
            st.session_state.new_session_sets = []

        col_fecha, col_notas = st.columns([1, 2])
        with col_fecha:
            session_date = st.date_input(
                "Fecha",
                value=date.today(),
                format="YYYY-MM-DD",
            )
        with col_notas:
            session_notes = st.text_input(
                "Notas de la sesión (opcional)",
                placeholder="Ej: me sentí fuerte, buen ritmo...",
            )

        st.divider()

        movements    = get_all_movements()
        classics     = [m["name"] for m in movements if m["category"] == "classic"]
        variants     = [m["name"] for m in movements if m["category"] == "variant"]
        accessory    = [m["name"] for m in movements if m["category"] == "accessory"]
        mv_ordered   = classics + variants + accessory

        col_mv, col_peso, col_series, col_reps, col_rpe, col_btn = st.columns([3, 2, 1, 1, 1, 1])

        with col_mv:
            selected_mv = st.selectbox(
                "Ejercicio",
                options=mv_ordered,
                key="set_movement",
            )
        with col_peso:
            weight_kg = st.number_input(
                "Peso (kg)",
                min_value=0.5, max_value=300.0,
                value=60.0, step=0.5,
                key="set_weight",
            )
        with col_series:
            series = st.number_input(
                "Series",
                min_value=1, max_value=10,
                value=1, step=1,
                key="set_series",
            )
        with col_reps:
            reps = st.number_input(
                "Reps",
                min_value=1, max_value=10,
                value=3, step=1,
                key="set_reps",
            )
        with col_rpe:
            rpe = st.number_input(
                "RPE",
                min_value=6.0, max_value=10.0,
                value=8.0, step=0.5,
                key="set_rpe",
            )
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("＋ Agregar", use_container_width=True, type="primary"):
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
            st.caption(f"**{len(st.session_state.new_session_sets)} sets en esta sesión:**")

            current_1rms_local = get_current_1rms()

            for i, s in enumerate(st.session_state.new_session_sets):
                col_s1, col_s2, col_s3, col_s4, col_s5, col_del = st.columns([3, 2, 1, 1, 1, 1])

                pct_str = "—"
                if s["movement"] in current_1rms_local:
                    pct     = (s["weight_kg"] / current_1rms_local[s["movement"]]["weight_kg"]) * 100
                    pct_str = f"{pct:.0f}%"

                with col_s1:
                    st.write(f"**{s['set_order']}.** {s['movement']}")
                with col_s2:
                    st.write(f"{s['weight_kg']} kg")
                with col_s3:
                    st.write(f"×{s['reps']}")
                with col_s4:
                    st.write(f"RPE {s['rpe']}")
                with col_s5:
                    st.write(pct_str)
                with col_del:
                    if st.button("✕", key=f"del_set_{i}"):
                        st.session_state.new_session_sets.pop(i)
                        for j, set_ in enumerate(st.session_state.new_session_sets):
                            set_["set_order"] = j + 1
                        st.rerun()

            st.divider()

            tonnage_session = sum(s["weight_kg"] * s["reps"] for s in st.session_state.new_session_sets)
            st.metric("Tonelaje de esta sesión", f"{tonnage_session:.0f} kg")

            col_guardar, col_limpiar = st.columns(2)
            with col_guardar:
                if st.button("💾 Guardar sesión", use_container_width=True, type="primary"):
                    session_uuid = str(uuid.uuid4())
                    session_id   = insert_session(
                        session_uuid=session_uuid,
                        session_date=session_date.strftime("%Y-%m-%d"),
                        notes=session_notes,
                        source="manual",
                    )
                    if session_id:
                        for s in st.session_state.new_session_sets:
                            insert_set(
                                session_id=session_id,
                                movement_name=s["movement"],
                                weight_kg=s["weight_kg"],
                                reps=s["reps"],
                                set_order=s["set_order"],
                                rpe=s["rpe"],
                            )
                        n_sets  = len(st.session_state.new_session_sets)
                        st.session_state.new_session_sets = []
                        st.success(f"✅ Sesión guardada — {n_sets} sets · {tonnage_session:.0f} kg tonelaje")
                        st.rerun()

            with col_limpiar:
                if st.button("🗑️ Limpiar", use_container_width=True):
                    st.session_state.new_session_sets = []
                    st.rerun()
        else:
            st.caption("Agrega el primer set 👆")

    with tab_historial:
        sessions = get_recent_sessions(limit=30)

        if not sessions:
            st.info("📭 Sin sesiones registradas aún.")
            st.caption("Usa la pestaña **Registrar sesión** para agregar tu primer entrenamiento.")
        else:
            st.caption(f"{len(sessions)} sesiones · más reciente primero")
            current_1rms_local = get_current_1rms()

            for sess in sessions:
                n_sets  = len(sess["sets"])
                tonnage = sum(s["weight_kg"] * s["reps"] for s in sess["sets"])
                src_icon = "📱" if sess.get("source") == "pwa" else "💻"
                header  = f"{src_icon} {sess['date']}  ·  {n_sets} sets  ·  {tonnage:.0f} kg"

                with st.expander(header):
                    if sess["notes"]:
                        st.caption(f"📝 {sess['notes']}")

                    if sess["sets"]:
                        df_sets    = pd.DataFrame(sess["sets"])
                        df_display = df_sets[["set_order", "movement", "weight_kg", "reps", "rpe"]].copy()
                        df_display.columns = ["#", "Ejercicio", "Peso (kg)", "Reps", "RPE"]
                        df_display["#"]    = range(1, len(df_display) + 1)

                        def calc_pct(row):
                            mv = row["Ejercicio"]
                            if mv in current_1rms_local:
                                pct = (row["Peso (kg)"] / current_1rms_local[mv]["weight_kg"]) * 100
                                return f"{pct:.0f}%"
                            return "—"

                        df_display["% 1RM"] = df_display.apply(calc_pct, axis=1)

                        col_t, col_m = st.columns([3, 1])
                        with col_t:
                            st.dataframe(df_display, use_container_width=True, hide_index=True)
                        with col_m:
                            st.metric("Tonelaje", f"{tonnage:.0f} kg")
                            st.metric("Sets",     n_sets)


# ─────────────────────────────────────────────────────────────
# PÁGINA: HERRAMIENTAS
# ─────────────────────────────────────────────────────────────

elif page == "📐 Herramientas":
    st.title("📐 Herramientas")

    tab_prilepin, tab_brzycki, tab_1rm = st.tabs([
        "📊 Calculadora Prilepin",
        "🔢 Estimador 1RM",
        "🏆 Registro 1RM",
    ])

    with tab_prilepin:
        st.subheader("Calculadora de Zonas Prilepin")
        st.caption("Calcula el rango de trabajo óptimo para cada zona de intensidad según tus 1RM.")

        current_1rms = get_current_1rms()

        col_mv, col_pct = st.columns(2)
        with col_mv:
            mv_options  = list(current_1rms.keys()) if current_1rms else ["Snatch", "Clean & Jerk"]
            prilepin_mv = st.selectbox("Movimiento", options=mv_options, key="prilepin_mv")
        with col_pct:
            intensity = st.slider("Intensidad (%1RM)", min_value=60, max_value=100, value=80, step=1)

        if prilepin_mv in current_1rms:
            one_rm     = current_1rms[prilepin_mv]["weight_kg"]
            weight_abs = round(one_rm * intensity / 100, 1)

            if intensity >= 90:
                zona = "Máxima (90%+)"; reps_opt = "7-10"; reps_max = 14; reps_serie = "1-2"
            elif intensity >= 80:
                zona = "Alta (80-89%)"; reps_opt = "15-20"; reps_max = 24; reps_serie = "2-4"
            elif intensity >= 70:
                zona = "Moderada (70-79%)"; reps_opt = "18-24"; reps_max = 30; reps_serie = "3-6"
            else:
                zona = "Técnica (<70%)"; reps_opt = "Sin límite"; reps_max = None; reps_serie = "3-6"

            st.divider()
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            with col_r1:
                st.metric("Peso de trabajo",       f"{weight_abs} kg")
            with col_r2:
                st.metric("Zona",                  zona)
            with col_r3:
                st.metric("Reps óptimas totales",  reps_opt)
            with col_r4:
                st.metric("Reps por serie",         reps_serie)

            if reps_max:
                st.caption(f"⚠️ No superar **{reps_max} repeticiones totales** en esta zona.")

            st.divider()
            st.subheader("Distribución sugerida")

            reps_per_set_map = {"1-2": [1, 2], "2-4": [2, 3], "3-6": [3, 4, 5]}
            reps_options     = reps_per_set_map.get(reps_serie, [3])
            suggestions      = []

            for r in reps_options:
                if reps_max:
                    opt_series = int(reps_opt.split("-")[1]) // r if "-" in reps_opt else reps_max // r
                    suggestions.append({
                        "Reps/serie":      r,
                        "Series óptimas":  opt_series,
                        "Series máximas":  reps_max // r,
                        "Peso (kg)":       weight_abs,
                        "Tonelaje óptimo": f"{opt_series * r * weight_abs:.0f} kg",
                    })

            if suggestions:
                st.dataframe(pd.DataFrame(suggestions), use_container_width=True, hide_index=True)
        else:
            st.info(f"No hay 1RM registrado para **{prilepin_mv}**. Regístralo en la pestaña **Registro 1RM**.")

    with tab_brzycki:
        st.subheader("Estimador de 1RM — Fórmula Brzycki")
        st.caption("Estima tu 1RM a partir de un set submáximo (válido para 1-5 reps).")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            brzycki_weight = st.number_input("Peso levantado (kg)", min_value=1.0, max_value=300.0, value=80.0, step=0.5)
        with col_b2:
            brzycki_reps   = st.number_input("Repeticiones realizadas", min_value=1, max_value=5, value=3, step=1)

        if brzycki_reps == 1:
            estimated = brzycki_weight
            st.info("Para 1 repetición, el peso levantado ES el 1RM.")
        else:
            estimated = brzycki_weight * 36 / (37 - brzycki_reps)

        st.metric("1RM Estimado", f"{estimated:.2f} kg")

        st.divider()
        st.caption("Tabla de porcentajes basada en este 1RM:")
        pcts   = [100, 95, 90, 85, 80, 75, 70]
        df_pct = pd.DataFrame({
            "% 1RM":     [f"{p}%" for p in pcts],
            "Peso (kg)": [round(estimated * p / 100, 1) for p in pcts],
        })
        st.dataframe(df_pct, use_container_width=True, hide_index=True)

    with tab_1rm:
        st.subheader("Registro Manual de 1RM")
        st.caption("Ingresa tus 1RM actuales o históricos. Útil para cargar datos previos a empezar a usar la app.")

        with st.form("form_1rm_manual"):
            col_m, col_w, col_d = st.columns([3, 2, 2])

            with col_m:
                movements_list = get_all_movements()
                mv_names_all   = [m["name"] for m in movements_list]
                mv_1rm         = st.selectbox("Movimiento", options=mv_names_all, key="1rm_movement")
            with col_w:
                weight_1rm = st.number_input("Peso (kg)", min_value=1.0, max_value=400.0, value=80.0, step=0.5)
            with col_d:
                fecha_1rm  = st.date_input("Fecha", value=date.today(), format="YYYY-MM-DD")

            if st.form_submit_button("💾 Guardar 1RM", use_container_width=True, type="primary"):
                save_manual_1rm(
                    movement_name=mv_1rm,
                    weight_kg=float(weight_1rm),
                    recorded_date=fecha_1rm.strftime("%Y-%m-%d"),
                )
                st.success(f"✅ 1RM guardado: {mv_1rm} → {weight_1rm} kg ({fecha_1rm})")
                st.rerun()

        st.divider()
        st.subheader("1RM Actuales Registrados")

        current_1rms_tool = get_current_1rms()

        if not current_1rms_tool:
            st.info("Sin 1RM registrados aún. Usa el formulario de arriba.")
        else:
            df_1rms = pd.DataFrame([
                {
                    "Movimiento": mv,
                    "1RM (kg)":   data["weight_kg"],
                    "Fecha":      data["date"],
                    "Fuente":     "✅ Real" if data["source"] == "actual" else "📐 Estimado",
                }
                for mv, data in current_1rms_tool.items()
            ])
            st.dataframe(df_1rms, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Progresión Histórica de 1RM")

        if current_1rms_tool:
            mv_hist = st.selectbox("Ver progresión de:", options=list(current_1rms_tool.keys()))
            history = get_1rm_history_by_movement(mv_hist)

            if len(history) > 1:
                df_hist  = pd.DataFrame(history)
                fig_1rm  = px.line(
                    df_hist, x="date", y="weight_kg",
                    markers=True,
                    title=f"Progresión 1RM — {mv_hist}",
                    labels={"date": "Fecha", "weight_kg": "1RM (kg)"},
                    color_discrete_sequence=["#C9A84C"],
                )
                fig_1rm.update_layout(
                    height=300,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#fafafa",
                    showlegend=False,
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
                )
                st.plotly_chart(fig_1rm, use_container_width=True)
            elif len(history) == 1:
                st.info(f"Solo hay un registro. Se necesitan al menos 2 puntos para mostrar la progresión.")

        st.divider()
        with st.expander("⚠️ Borrar registros de 1RM"):
            st.caption("Elimina TODOS los registros de 1RM para el movimiento seleccionado. No se puede deshacer.")
            col_del, col_btn_del = st.columns([3, 1])
            with col_del:
                mv_names_all2 = [m["name"] for m in get_all_movements()]
                mv_to_delete  = st.selectbox("Movimiento a borrar", options=mv_names_all2, key="delete_1rm_mv")
            with col_btn_del:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Borrar", key="btn_delete_1rm", use_container_width=True):
                    delete_1rm(mv_to_delete)
                    st.warning(f"1RM de {mv_to_delete} eliminado.")
                    st.rerun()


# ─────────────────────────────────────────────────────────────
# PÁGINA: ENTRENADOR IA
# ─────────────────────────────────────────────────────────────

elif page == "🤖 Entrenador IA":
    st.title("🤖 Entrenador IA")
    st.caption("Powered by Claude · Razona sobre tus datos reales de entrenamiento")

    if not profile_is_complete():
        st.warning("⚠️ Completa tu **Perfil** antes de usar el entrenador.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    col_ctx, col_clear = st.columns([5, 1])
    with col_ctx:
        with st.expander("👁️ Ver contexto actual del entrenador"):
            try:
                st.code(build_athlete_context(), language=None)
            except Exception as e:
                st.error(f"Error: {e}")
    with col_clear:
        if st.button("🗑️ Limpiar", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()

    st.caption("Sugerencias:")
    sq_cols  = st.columns(3)
    quick_qs = [
        "¿Qué sesión me recomiendas para mañana?",
        "Analiza mi progresión de las últimas semanas",
        "¿Qué modelo de periodización me sugerirías?",
    ]
    for i, (col, q) in enumerate(zip(sq_cols, quick_qs)):
        with col:
            if st.button(q, key=f"sq_{i}", use_container_width=True):
                st.session_state["_pending_q"] = q

    st.divider()

    for msg in st.session_state.chat_messages:
        avatar = "🏋️" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

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