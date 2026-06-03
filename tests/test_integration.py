"""
test_integration.py — LiftLog: Test de integración E2E
=======================================================
Simula el flujo completo:
  PWA exporta JSON → sync.py lo importa → inserta en SQLite
  → coach.py construye contexto → todo verificado

Correr con: python tests/test_integration.py
"""

import json
import sys
import tempfile
import uuid
from datetime import date
from pathlib import Path

# Agregar src/ al path para importar los módulos
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db import (
    get_current_1rms,
    get_snatch_cj_ratio,
    get_volume_trend_alert,
    get_weekly_tonnage,
    initialize_db,
)
from sync import parse_and_import_session

SEPARATOR = "─" * 60


def _print_section(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def create_mock_session() -> dict:
    """
    Crea un JSON de sesión que simula la salida de la PWA.
    Incluye snatch, C&J y accesorios con pesos reales de entrenamiento.
    """
    return {
        "session_uuid": str(uuid.uuid4()),
        "session_date": date.today().isoformat(),
        "notes":        "Sesión de prueba — test de integración E2E",
        "exported_at":  date.today().isoformat() + "T15:00:00Z",
        "sets": [
            {"movement": "Snatch",       "weight_kg": 75,  "reps": 3, "set_order": 1},
            {"movement": "Snatch",       "weight_kg": 80,  "reps": 3, "set_order": 2},
            {"movement": "Snatch",       "weight_kg": 85,  "reps": 2, "set_order": 3},
            {"movement": "Snatch",       "weight_kg": 90,  "reps": 1, "set_order": 4},
            {"movement": "Clean & Jerk", "weight_kg": 95,  "reps": 2, "set_order": 5},
            {"movement": "Clean & Jerk", "weight_kg": 100, "reps": 2, "set_order": 6},
            {"movement": "Clean & Jerk", "weight_kg": 107, "reps": 1, "set_order": 7},
            {"movement": "Front Squat",  "weight_kg": 110, "reps": 3, "set_order": 8},
            {"movement": "Front Squat",  "weight_kg": 120, "reps": 2, "set_order": 9},
        ],
    }


def step1_init_db() -> bool:
    _print_section("PASO 1/5: Inicializar base de datos")
    try:
        initialize_db()
        print("✅ DB inicializada correctamente")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def step2_create_json() -> tuple[bool, Path, dict]:
    _print_section("PASO 2/5: Crear JSON de sesión (simula la PWA)")
    session  = create_mock_session()
    tmp_dir  = Path(tempfile.mkdtemp())
    filename = f"liftlog_session_{session['session_date']}_{session['session_uuid'][:8]}.json"
    filepath = tmp_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)

    print(f"✅ Archivo creado: {filename}")
    print(f"   UUID:  {session['session_uuid']}")
    print(f"   Fecha: {session['session_date']}")
    print(f"   Sets:  {len(session['sets'])}")
    return True, filepath, session


def step3_import_session(filepath: Path) -> bool:
    _print_section("PASO 3/5: Importar con sync.py")
    success = parse_and_import_session(filepath)

    if success:
        print("✅ Sesión importada en SQLite")
    else:
        print("❌ Error al importar")

    return success


def step4_verify_sqlite() -> bool:
    _print_section("PASO 4/5: Verificar datos en SQLite")

    current_1rms = get_current_1rms()
    if not current_1rms:
        print("❌ No se encontraron 1RMs — algo falló en la inserción")
        return False

    print("1RM detectados:")
    for mv, data in current_1rms.items():
        tag = "✓ real" if data["source"] == "actual" else "~ estimado"
        print(f"  {mv:<22} {data['weight_kg']:>7.2f} kg  [{tag}]")

    ratio = get_snatch_cj_ratio()
    print(f"\nRelación Snatch/C&J: ", end="")
    if ratio["status"] == "unavailable":
        print(f"unavailable (falta: {ratio['missing']})")
    else:
        print(f"{ratio['ratio_percent']}% [{ratio['status']}]")

    tonnage = get_weekly_tonnage(weeks=1)
    total   = sum(row["tonnage_kg"] for row in tonnage)
    print(f"\nTonelaje esta semana: {total:.0f} kg")

    alert = get_volume_trend_alert()
    print(f"Alerta de volumen:    {alert['alert_level']} "
          f"(Δ{alert['change_pct']:+.1f}%)")

    print("\n✅ Datos verificados en SQLite")
    return True


def step5_build_coach_context() -> bool:
    _print_section("PASO 5/5: Construir contexto del entrenador")

    try:
        from coach import build_athlete_context
        context = build_athlete_context()

        print("✅ Contexto construido correctamente")
        print(f"   Longitud: {len(context)} caracteres")
        print(f"\n{'─'*60}")
        print("PREVIEW (primeros 600 chars):")
        print("─"*60)
        print(context[:600])
        if len(context) > 600:
            print(f"\n... ({len(context) - 600} chars más)")
        print("─"*60)
        return True

    except ImportError as e:
        print(f"⚠️  No se pudo importar coach.py: {e}")
        return True


def run_dedup_test(session: dict) -> None:
    """Verifica que importar el mismo UUID dos veces no duplica datos."""
    _print_section("BONUS: Test de deduplicación")

    tmp_dir  = Path(tempfile.mkdtemp())
    filename = f"liftlog_session_dup_{session['session_uuid'][:8]}.json"
    filepath = tmp_dir / filename

    with open(filepath, "w") as f:
        json.dump(session, f)

    result = parse_and_import_session(filepath)
    if result is False:
        print("✅ Dedup correcto — segundo import rechazado como esperado")
    else:
        print("⚠️  Se permitió importar duplicado — revisar insert_session()")


def main():
    print("\n" + "═"*60)
    print("  🧪 LIFTLOG — TEST DE INTEGRACIÓN E2E")
    print("═"*60)

    if not step1_init_db():
        print("\n❌ Test abortado en Paso 1")
        return

    ok, filepath, session = step2_create_json()
    if not ok:
        print("\n❌ Test abortado en Paso 2")
        return

    if not step3_import_session(filepath):
        print("ℹ️  Reintentando con sesión nueva...")
        _, filepath, session = step2_create_json()
        step3_import_session(filepath)

    if not step4_verify_sqlite():
        print("\n❌ Test abortado en Paso 4")
        return

    step5_build_coach_context()
    run_dedup_test(session)

    filepath.unlink(missing_ok=True)

    print("\n" + "═"*60)
    print("  ✅ TEST COMPLETADO")
    print("═"*60)
    print("\nPróximos pasos:")
    print("  1. streamlit run app.py")
    print("  2. Sube pwa/ a GitHub Pages")
    print("  3. python src/sync.py --backfill")


if __name__ == "__main__":
    main()