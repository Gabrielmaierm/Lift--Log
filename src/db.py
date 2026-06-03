"""
db.py — LiftLog: Capa de base de datos
======================================
Responsabilidades:
  · Crear y mantener el schema SQLite
  · Insertar sesiones y sets (con dedup por UUID)
  · Actualizar automáticamente 1RM cuando se registra un nuevo máximo
  · Proveer las queries analíticas que usa tanto app.py como coach.py

No usa ORM: sqlite3 de la librería estándar, queries explícitas y comentadas.
"""

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE PATHS
# ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = Path(os.getenv("LIFTLOG_DB_PATH", str(BASE_DIR / "data" / "liftlog.db")))


# ─────────────────────────────────────────────────────────────
# CATÁLOGO DE MOVIMIENTOS (seed data)
# ─────────────────────────────────────────────────────────────

MOVEMENTS_SEED: list[tuple[str, str]] = [
    ("Snatch",              "classic"),
    ("Clean & Jerk",        "classic"),
    ("Hang Snatch",         "variant"),
    ("Power Snatch",        "variant"),
    ("Hang Power Snatch",   "variant"),
    ("Mid-Hang Clean",      "variant"),
    ("Squat Clean",         "variant"),
    ("Power Clean",         "variant"),
    ("Split Jerk",          "variant"),
    ("Push Jerk",           "variant"),
    ("Clean",               "variant"),
    ("Front Squat",         "accessory"),
    ("Back Squat",          "accessory"),
    ("Romanian Deadlift",   "accessory"),
    ("Snatch Pull",         "accessory"),
    ("Clean Pull",          "accessory"),
    ("Overhead Squat",      "accessory"),
    ("Snatch Balance",      "accessory"),
    ("Jerk from Rack",      "accessory"),
]


# ─────────────────────────────────────────────────────────────
# CONEXIÓN
# ─────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """
    Retorna una conexión SQLite configurada.
    - row_factory = sqlite3.Row  → acceso por nombre: row["columna"]
    - foreign_keys = ON          → activa integridad referencial
    - journal_mode = WAL         → lecturas no bloquean escrituras
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ─────────────────────────────────────────────────────────────
# INICIALIZACIÓN DEL SCHEMA
# ─────────────────────────────────────────────────────────────

def initialize_db() -> None:
    """
    Crea todas las tablas, índices y siembra los movimientos predefinidos.
    Idempotente: llamar múltiples veces no destruye ni duplica datos.
    """
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS movements (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL UNIQUE,
            category TEXT    NOT NULL
                     CHECK(category IN ('classic', 'variant', 'accessory'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_uuid TEXT    NOT NULL UNIQUE,
            session_date TEXT    NOT NULL,
            notes        TEXT    DEFAULT '',
            source       TEXT    DEFAULT 'pwa',
            imported_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            movement_id INTEGER NOT NULL,
            weight_kg   REAL    NOT NULL CHECK(weight_kg > 0),
            reps        INTEGER NOT NULL CHECK(reps BETWEEN 1 AND 20),
            set_order   INTEGER,
            rpe         REAL    CHECK(rpe IS NULL OR rpe BETWEEN 6 AND 10),
            notes       TEXT    DEFAULT '',
            FOREIGN KEY (session_id)  REFERENCES sessions(id)  ON DELETE CASCADE,
            FOREIGN KEY (movement_id) REFERENCES movements(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS one_rm_history (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_id      INTEGER NOT NULL,
            weight_kg        REAL    NOT NULL,
            recorded_date    TEXT    NOT NULL,
            source           TEXT    NOT NULL
                             CHECK(source IN ('actual', 'estimated')),
            source_weight_kg REAL,
            source_reps      INTEGER,
            FOREIGN KEY (movement_id) REFERENCES movements(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS coach_conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role       TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
            content    TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_sets_movement  ON sets(movement_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sets_session   ON sets(session_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_date  ON sessions(session_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_1rm_movement   ON one_rm_history(movement_id, recorded_date DESC)")

    cur.executemany(
        "INSERT OR IGNORE INTO movements (name, category) VALUES (?, ?)",
        MOVEMENTS_SEED
    )

    conn.commit()
    conn.close()
    print(f"✅ DB inicializada: {DB_PATH}")


# ─────────────────────────────────────────────────────────────
# INSERCIÓN
# ─────────────────────────────────────────────────────────────

def insert_session(
    session_uuid: str,
    session_date: str,
    notes: str  = "",
    source: str = "pwa"
) -> Optional[int]:
    """
    Inserta una sesión nueva. Retorna su ID, o None si el UUID ya existía.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO sessions (session_uuid, session_date, notes, source)
            VALUES (?, ?, ?, ?)
            """,
            (session_uuid, session_date, notes, source)
        )
        conn.commit()

        if cur.rowcount == 0:
            print(f"⚠️  Sesión {session_uuid[:8]}... ya importada. Saltando.")
            return None

        session_id = cur.lastrowid
        print(f"✅ Sesión insertada → ID={session_id}, fecha={session_date}")
        return session_id
    finally:
        conn.close()


def _get_or_create_movement_id(name: str) -> int:
    """
    Retorna el ID del movimiento. Si no existe, lo crea como 'accessory'.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM movements WHERE name = ?", (name,)
        ).fetchone()

        if row:
            return row["id"]

        print(f"⚠️  Movimiento '{name}' no encontrado → insertando como accessory")
        cur = conn.execute(
            "INSERT OR IGNORE INTO movements (name, category) VALUES (?, 'accessory')",
            (name,)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_set(
    session_id:    int,
    movement_name: str,
    weight_kg:     float,
    reps:          int,
    set_order:     Optional[int]   = None,
    rpe:           Optional[float] = None,
    notes:         str             = ""
) -> int:
    """
    Inserta un set y dispara la actualización de 1RM si corresponde.
    """
    movement_id = _get_or_create_movement_id(movement_name)

    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO sets (session_id, movement_id, weight_kg, reps, set_order, rpe, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, movement_id, float(weight_kg), int(reps),
             set_order, rpe, notes)
        )
        conn.commit()
        set_id = cur.lastrowid
    finally:
        conn.close()

    _update_1rm_if_new_max(movement_id, weight_kg, reps)
    return set_id


def _update_1rm_if_new_max(movement_id: int, weight_kg: float, reps: int) -> None:
    """
    Calcula el 1RM estimado con Brzycki y lo guarda si supera el máximo histórico.
    Brzycki: 1RM = peso × 36 / (37 − reps). Solo para 1-5 reps.
    """
    if reps > 5:
        return

    if reps == 1:
        estimated_1rm = weight_kg
        source        = "actual"
    else:
        estimated_1rm = weight_kg * 36 / (37 - reps)
        source        = "estimated"

    estimated_1rm = round(estimated_1rm, 2)

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT weight_kg FROM one_rm_history
            WHERE movement_id = ?
            ORDER BY weight_kg DESC
            LIMIT 1
            """,
            (movement_id,)
        ).fetchone()

        current_max = row["weight_kg"] if row else 0.0

        if estimated_1rm > current_max:
            conn.execute(
                """
                INSERT INTO one_rm_history
                    (movement_id, weight_kg, recorded_date, source,
                     source_weight_kg, source_reps)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (movement_id, estimated_1rm, date.today().isoformat(),
                 source, weight_kg, reps)
            )
            conn.commit()
            print(f"🏆 Nuevo 1RM: movement_id={movement_id} → {estimated_1rm} kg ({source})")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# QUERIES ANALÍTICAS
# ─────────────────────────────────────────────────────────────

def get_current_1rms() -> dict:
    """
    Retorna el 1RM máximo histórico para cada movimiento registrado.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT m.name, r.weight_kg, r.recorded_date AS date, r.source
            FROM one_rm_history r
            JOIN movements m ON m.id = r.movement_id
            WHERE r.weight_kg = (
                SELECT MAX(weight_kg)
                FROM one_rm_history
                WHERE movement_id = r.movement_id
            )
            ORDER BY m.name
            """
        ).fetchall()

        return {
            row["name"]: {
                "weight_kg": row["weight_kg"],
                "date":      row["date"],
                "source":    row["source"],
            }
            for row in rows
        }
    finally:
        conn.close()


def get_weekly_tonnage(weeks: int = 8) -> list[dict]:
    """
    Tonelaje semanal por movimiento para las últimas N semanas.
    Tonelaje = Σ(weight_kg × reps) por movimiento por semana.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                strftime('%Y-W%W', s.session_date) AS week,
                m.name                             AS movement_name,
                m.category                         AS category,
                SUM(st.weight_kg * st.reps)        AS tonnage_kg,
                COUNT(st.id)                       AS set_count,
                SUM(st.reps)                       AS total_reps
            FROM sets st
            JOIN sessions  s ON s.id  = st.session_id
            JOIN movements m ON m.id  = st.movement_id
            WHERE s.session_date >= date('now', ? || ' days')
            GROUP BY week, m.name
            ORDER BY week DESC, tonnage_kg DESC
            """,
            (f"-{weeks * 7}",)
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_snatch_cj_ratio() -> dict:
    """
    Calcula la relación Snatch / Clean & Jerk con los 1RM actuales.
    """
    current = get_current_1rms()

    snatch = current.get("Snatch")
    cj     = current.get("Clean & Jerk")

    result: dict = {
        "snatch_1rm":    snatch["weight_kg"] if snatch else None,
        "cj_1rm":        cj["weight_kg"]     if cj     else None,
        "ratio_percent": None,
        "status":        "unavailable",
        "missing":       [],
    }

    if not snatch:
        result["missing"].append("Snatch")
    if not cj:
        result["missing"].append("Clean & Jerk")

    if snatch and cj:
        ratio                   = snatch["weight_kg"] / cj["weight_kg"]
        result["ratio_percent"] = round(ratio * 100, 1)

        if ratio < 0.78:
            result["status"] = "low"
        elif ratio > 0.84:
            result["status"] = "high"
        else:
            result["status"] = "ok"

    return result


def get_volume_trend_alert(lookback_weeks: int = 4) -> dict:
    """
    Compara tonelaje de los últimos 7 días vs. promedio de N semanas previas.
    """
    conn = get_connection()
    try:
        current = conn.execute(
            """
            SELECT COALESCE(SUM(st.weight_kg * st.reps), 0) AS tonnage
            FROM sets st
            JOIN sessions s ON s.id = st.session_id
            WHERE s.session_date >= date('now', '-7 days')
            """
        ).fetchone()

        prev = conn.execute(
            """
            SELECT AVG(weekly_tonnage) AS avg_tonnage FROM (
                SELECT
                    strftime('%Y-W%W', s.session_date) AS week,
                    SUM(st.weight_kg * st.reps)        AS weekly_tonnage
                FROM sets st
                JOIN sessions s ON s.id = st.session_id
                WHERE s.session_date <  date('now', '-7 days')
                  AND s.session_date >= date('now', :days_back || ' days')
                GROUP BY week
            )
            """,
            {"days_back": f"-{(lookback_weeks + 1) * 7}"}
        ).fetchone()

        current_kg = current["tonnage"] or 0.0
        avg_prev   = prev["avg_tonnage"] or 0.0

        if avg_prev == 0:
            change_pct  = 0.0
            alert_level = "no_data"
        else:
            change_pct = ((current_kg - avg_prev) / avg_prev) * 100

            if change_pct < -35:
                alert_level = "critical_drop"
            elif change_pct < -20:
                alert_level = "warning_drop"
            elif change_pct > 25:
                alert_level = "warning_spike"
            else:
                alert_level = "normal"

        return {
            "current_week_kg":   round(current_kg, 1),
            "avg_prev_weeks_kg": round(avg_prev,   1),
            "change_pct":        round(change_pct, 1),
            "alert_level":       alert_level,
            "lookback_weeks":    lookback_weeks,
        }
    finally:
        conn.close()


def get_recent_sessions(limit: int = 10) -> list[dict]:
    """
    Retorna las últimas N sesiones con todos sus sets incluidos.
    """
    conn = get_connection()
    try:
        sessions = conn.execute(
            """
            SELECT id, session_date AS date, notes, source
            FROM sessions
            ORDER BY session_date DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        result = []
        for sess in sessions:
            sets = conn.execute(
                """
                SELECT
                    st.set_order,
                    m.name   AS movement,
                    st.weight_kg,
                    st.reps,
                    st.rpe,
                    st.notes
                FROM sets st
                JOIN movements m ON m.id = st.movement_id
                WHERE st.session_id = ?
                ORDER BY COALESCE(st.set_order, st.id)
                """,
                (sess["id"],)
            ).fetchall()

            result.append({
                **dict(sess),
                "sets": [dict(s) for s in sets],
            })

        return result
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# HISTORIAL DEL ENTRENADOR
# ─────────────────────────────────────────────────────────────

def save_coach_message(role: str, content: str) -> None:
    """Guarda un mensaje del historial de conversación con el coach."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO coach_conversations (role, content) VALUES (?, ?)",
            (role, content)
        )
        conn.commit()
    finally:
        conn.close()


def get_coach_history(last_n: int = 6) -> list[dict]:
    """
    Recupera los últimos N mensajes del historial en orden cronológico.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT role, content FROM coach_conversations
            ORDER BY id DESC
            LIMIT ?
            """,
            (last_n,)
        ).fetchall()

        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    finally:
        conn.close()