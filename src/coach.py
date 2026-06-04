"""
coach.py — LiftLog: Motor del entrenador inteligente
====================================================
Responsabilidades:
  1. build_athlete_context(): extrae datos de SQLite incluyendo
     el perfil del atleta y construye el contexto para Claude
  2. ask_coach(): llama a Claude API con ese contexto + historial
"""

import os
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from db import (
    get_athlete_profile,
    get_coach_history,
    get_current_1rms,
    get_recent_sessions,
    get_snatch_cj_ratio,
    get_volume_trend_alert,
    get_weekly_tonnage,
    save_coach_message,
)

load_dotenv()


# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────

COACH_SYSTEM_PROMPT = """Eres un entrenador de halterofilia olímpica con 15+ años de experiencia con atletas competidores de nivel amateur y nacional. Tienes formación en ciencias del deporte y dominas los modelos de periodización validados para halterofilia.

## ROL
Razonas sobre los datos REALES del atleta que se te proporcionan al final de este prompt. No haces recomendaciones en abstracto. Si los datos son insuficientes para una recomendación específica, lo dices y explicas qué información falta.

## CONOCIMIENTO TÉCNICO

### Tablas de Prilepin (adaptadas a halterofilia olímpica)
| % 1RM   | Reps óptimas totales | Máximo | Reps por serie |
|---------|----------------------|--------|----------------|
| 70-79%  | 18-24                | 30     | 3-6            |
| 80-89%  | 15-20                | 24     | 2-4            |
| 90%+    | 7-10                 | 14     | 1-2            |

### Relación Snatch / Clean & Jerk
- Rango esperado (atleta amateur): 78-84%
- < 78%: déficit técnico en snatch o exceso de fuerza relativa en clean & jerk
- > 84%: posible debilidad en el jerk o déficit de fuerza de empuje
- Si cualquiera de los dos 1RM es null: NO hagas afirmaciones sobre la relación.

### Fórmula 1RM
- Brzycki (1-5 reps): 1RM = peso × 36 / (37 − reps)
- Para 1 rep: el peso registrado ES el 1RM
- Para 6+ reps: estimación no confiable en movimientos olímpicos

### Periodización (sin modelo formal → proponer lineal por bloques)
- Acumulación (4-6 sem): volumen alto, 70-80% 1RM, énfasis en técnica
- Intensificación (3-4 sem): volumen moderado, intensidad creciente 80-90%
- Realización (2-3 sem): volumen bajo, 90%+, pico competitivo
- Descarga: cada 4ª semana, reducir 40-50% el volumen total

### Alertas de volumen
- Caída >20% vs. media 4 semanas previas: señal de alerta
- Caída >35%: sobreentrenamiento, lesión oculta o fatiga severa
- Aumento >25% en una semana: riesgo de carga excesiva

### Categorías de peso IWF — contexto para prescripción de cargas
Las cargas absolutas deben interpretarse siempre en relación a la
categoría de peso del atleta. Un snatch de 90 kg es diferente para
un atleta de 67 kg que para uno de 96 kg.

## COMPORTAMIENTO
- Usa % 1RM al prescribir cargas y calcula el peso absoluto con los datos del atleta
  Formato: "3×2 al 82% = X kg"
- Cita el fundamento (Prilepin, periodización, evidencia) cuando sea relevante
- Tono directo y técnico, sin sobreexplicar conceptos básicos
- Si detectas una tendencia preocupante, la mencionas aunque no te la hayan preguntado
- Si el estado es "Retorno de lesión" o "Lesión activa": prioriza progresión conservadora
- Si hay fecha de competencia: orienta las recomendaciones hacia ese objetivo
- Para prescribir sesiones usa este formato:
  Ejercicio: X series × Y reps al Z% (= W kg)"""


# ─────────────────────────────────────────────────────────────
# CONSTRUCCIÓN DEL CONTEXTO DINÁMICO
# ─────────────────────────────────────────────────────────────

def build_athlete_context() -> str:
    """
    Extrae datos del atleta desde SQLite y construye el bloque de contexto
    que se adjunta al system prompt en cada llamada a la API.

    Incluye:
    - Perfil completo del atleta (desde athlete_profile)
    - 1RM actuales
    - Relación snatch/C&J
    - Tonelaje semanal últimas 4 semanas
    - Alerta de volumen
    - Resumen de las 3 últimas sesiones
    """
    today   = date.today().isoformat()
    profile = get_athlete_profile()

    current_1rms    = get_current_1rms()
    ratio           = get_snatch_cj_ratio()
    tonnage_data    = get_weekly_tonnage(weeks=6)
    volume_alert    = get_volume_trend_alert(lookback_weeks=4)
    recent_sessions = get_recent_sessions(limit=3)

    # ── Formatear perfil del atleta ──────────────────────────
    nombre    = profile.get("nombre")    or "Sin nombre"
    edad      = profile.get("edad")
    genero    = profile.get("genero")    or "—"
    cat_peso  = profile.get("categoria_peso") or "Sin definir"
    años_exp  = profile.get("años_experiencia") or 0
    federacion = profile.get("federacion") or "—"
    nivel     = profile.get("nivel_competitivo") or "—"
    fecha_comp = profile.get("fecha_competencia")
    estado    = profile.get("estado_entrenamiento") or "Normal"
    notas_add = profile.get("notas_adicionales") or ""

    edad_str  = f"{edad} años" if edad else "—"

    # Calcular semanas hasta competencia si hay fecha
    if fecha_comp:
        try:
            from datetime import datetime
            delta = datetime.strptime(fecha_comp, "%Y-%m-%d") - datetime.today()
            semanas_comp = max(0, delta.days // 7)
            comp_str = f"{fecha_comp} ({semanas_comp} semanas)"
        except Exception:
            comp_str = fecha_comp
    else:
        comp_str = "Sin competencia programada"

    # Estado con ícono
    estado_icons = {
        "Normal":            "✓",
        "Retorno de lesión": "⚠️",
        "Lesión activa":     "🚨",
    }
    estado_str = f"{estado_icons.get(estado, '—')} {estado}"

    profile_block = f"""  Nombre:              {nombre}
  Edad:                {edad_str}
  Género:              {genero}
  Categoría de peso:   {cat_peso} kg
  Experiencia:         {años_exp} año(s) en halterofilia
  Federación:          {federacion}
  Nivel competitivo:   {nivel}
  Próxima competencia: {comp_str}
  Estado actual:       {estado_str}"""

    if notas_add:
        profile_block += f"\n  Notas del atleta:    {notas_add}"

    # ── Formatear 1RMs ───────────────────────────────────────
    if current_1rms:
        lines    = []
        priority = ["Snatch", "Clean & Jerk", "Front Squat", "Back Squat"]
        ordered  = [k for k in priority if k in current_1rms]
        ordered += [k for k in current_1rms if k not in priority]

        for name in ordered:
            d   = current_1rms[name]
            tag = "✓" if d["source"] == "actual" else "~est"
            lines.append(f"  {name:<22} {d['weight_kg']:>6} kg  [{tag}, {d['date']}]")
        ones_rm_block = "\n".join(lines)
    else:
        ones_rm_block = "  Sin 1RM registrados aún"

    # ── Formatear relación snatch/C&J ────────────────────────
    if ratio["status"] == "unavailable":
        missing_str = " y ".join(ratio["missing"])
        ratio_block = f"  null — falta 1RM de: {missing_str}"
    else:
        status_labels = {"ok": "✓ normal", "low": "⚠ bajo", "high": "⚠ alto"}
        ratio_block = (
            f"  {ratio['ratio_percent']}%  "
            f"[{status_labels.get(ratio['status'], ratio['status'])}]  "
            f"(rango esperado amateur: 78-84%)"
        )

    # ── Formatear tonelaje semanal ───────────────────────────
    if tonnage_data:
        weekly_totals: dict[str, float] = {}
        for row in tonnage_data:
            weekly_totals[row["week"]] = (
                weekly_totals.get(row["week"], 0) + row["tonnage_kg"]
            )

        recent_weeks  = sorted(weekly_totals, reverse=True)[:4]
        tonnage_lines = [
            f"  {w}: {weekly_totals[w]:>8.0f} kg total"
            for w in recent_weeks
        ]

        top2_weeks = set(recent_weeks[:2])
        mv_vol: dict[str, float] = {}
        for row in tonnage_data:
            if row["week"] in top2_weeks:
                mv_vol[row["movement_name"]] = (
                    mv_vol.get(row["movement_name"], 0) + row["tonnage_kg"]
                )
        top_mv     = sorted(mv_vol.items(), key=lambda x: x[1], reverse=True)[:4]
        top_mv_str = "  " + " | ".join(f"{mv}: {t:.0f} kg" for mv, t in top_mv)

        tonnage_block = "\n".join(tonnage_lines) + f"\n  Top movimientos (2 sem):\n{top_mv_str}"
    else:
        tonnage_block = "  Sin datos de tonelaje aún"

    # ── Formatear alerta de volumen ──────────────────────────
    alert_labels = {
        "normal":        "✓ Normal",
        "warning_drop":  "⚠ Caída >20% — monitorear",
        "critical_drop": "🚨 Caída >35% — revisar urgente",
        "warning_spike": "⚠ Aumento >25% — riesgo carga excesiva",
        "no_data":       "— Sin datos suficientes",
    }
    alert_block = (
        f"  Última semana: {volume_alert['current_week_kg']} kg | "
        f"Promedio {volume_alert['lookback_weeks']} sem previas: "
        f"{volume_alert['avg_prev_weeks_kg']} kg | "
        f"Δ {volume_alert['change_pct']:+.1f}%\n"
        f"  Estado: {alert_labels.get(volume_alert['alert_level'], 'Desconocido')}"
    )

    # ── Formatear sesiones recientes ─────────────────────────
    if recent_sessions:
        sess_lines = []
        for sess in recent_sessions:
            sets_preview = ", ".join(
                f"{s['movement']} {s['weight_kg']}×{s['reps']}"
                for s in sess["sets"][:5]
            )
            if len(sess["sets"]) > 5:
                sets_preview += f" (+{len(sess['sets'])-5} más)"
            sess_lines.append(f"  {sess['date']}: {sets_preview}")
        sessions_block = "\n".join(sess_lines)
    else:
        sessions_block = "  Sin sesiones registradas aún"

    # ── Construir bloque final ───────────────────────────────
    context = f"""
════════════════════════════════════════════
PERFIL DEL ATLETA — {today}
════════════════════════════════════════════
{profile_block}

── 1RM ACTUALES ──────────────────────────────
{ones_rm_block}

── RELACIÓN SNATCH / CLEAN & JERK ────────────
{ratio_block}

── TONELAJE SEMANAL (últimas 4 semanas) ──────
{tonnage_block}

── ALERTA DE VOLUMEN ─────────────────────────
{alert_block}

── SESIONES RECIENTES (últimas 3) ────────────
{sessions_block}
════════════════════════════════════════════"""

    return context.strip()


# ─────────────────────────────────────────────────────────────
# LLAMADA A CLAUDE API
# ─────────────────────────────────────────────────────────────

def ask_coach(user_question: str) -> str:
    """
    Envía una pregunta al entrenador IA con el contexto completo del atleta.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "❌ ANTHROPIC_API_KEY no configurada. Agrega tu API key al archivo .env"

    athlete_context = build_athlete_context()
    full_system     = f"{COACH_SYSTEM_PROMPT}\n\n{athlete_context}"
    history         = get_coach_history(last_n=6)
    messages        = history + [{"role": "user", "content": user_question}]

    try:
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=full_system,
            messages=messages,
        )
        answer = response.content[0].text

    except anthropic.APIConnectionError:
        return "❌ Sin conexión. El entrenador requiere internet para funcionar."
    except anthropic.AuthenticationError:
        return "❌ API key inválida. Verifica ANTHROPIC_API_KEY en .env"
    except anthropic.RateLimitError:
        return "⚠️  Rate limit alcanzado. Espera un momento e inténtalo de nuevo."
    except Exception as e:
        return f"❌ Error inesperado: {str(e)}"

    save_coach_message("user",      user_question)
    save_coach_message("assistant", answer)

    return answer