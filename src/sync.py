"""
sync.py — LiftLog: Motor de sincronización
==========================================
Monitorea la carpeta de iCloud Drive con watchdog.
Cuando detecta un archivo JSON exportado desde la PWA:
  1. Valida la estructura del archivo
  2. Parsea los datos
  3. Inserta en SQLite vía db.py (con dedup por UUID)

Uso:
  python src/sync.py                 # Inicia el watcher
  python src/sync.py --backfill      # Importa archivos existentes + inicia watcher
  python src/sync.py --folder /ruta/ # Usa carpeta custom
"""

import json
import os
import re
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

sys.path.insert(0, str(Path(__file__).parent))
from db import initialize_db, insert_session, insert_set

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────

_DEFAULT_ICLOUD = (
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "com~apple~CloudDocs"
    / "LiftLog"
)

SYNC_FOLDER  = Path(os.getenv("ICLOUD_SYNC_FOLDER", str(_DEFAULT_ICLOUD))).expanduser()
FILE_PATTERN = re.compile(r"liftlog_session_[\w\-]+\.json$")


# ─────────────────────────────────────────────────────────────
# VALIDACIÓN DEL JSON
# ─────────────────────────────────────────────────────────────

def validate_session_json(data: dict) -> tuple[bool, str]:
    """
    Verifica que el JSON exportado por la PWA tiene la estructura esperada.

    Estructura requerida:
      {
        "session_uuid": "uuid-v4",
        "session_date": "YYYY-MM-DD",
        "notes":        "...",
        "exported_at":  "ISO8601",
        "sets": [
          {
            "movement":  "Snatch",
            "weight_kg": 80.0,
            "reps":      3,
            "set_order": 1,
            "notes":     ""
          }
        ]
      }
    """
    for field in ("session_uuid", "session_date", "sets"):
        if field not in data:
            return False, f"Campo faltante: '{field}'"

    try:
        datetime.strptime(data["session_date"], "%Y-%m-%d")
    except ValueError:
        return False, f"Fecha inválida: '{data['session_date']}' (esperado YYYY-MM-DD)"

    if not isinstance(data["sets"], list) or len(data["sets"]) == 0:
        return False, "La sesión no contiene sets"

    for i, s in enumerate(data["sets"], start=1):
        for field in ("movement", "weight_kg", "reps"):
            if field not in s:
                return False, f"Set {i}: campo faltante '{field}'"

        if not isinstance(s["weight_kg"], (int, float)) or s["weight_kg"] <= 0:
            return False, f"Set {i}: weight_kg debe ser un número positivo"

        if not isinstance(s["reps"], int) or not (1 <= s["reps"] <= 20):
            return False, f"Set {i}: reps debe ser entero entre 1 y 20"

    return True, ""


# ─────────────────────────────────────────────────────────────
# IMPORTACIÓN DE SESIÓN
# ─────────────────────────────────────────────────────────────

def parse_and_import_session(filepath: Path) -> bool:
    """
    Lee un JSON de sesión, lo valida e importa a SQLite.

    Returns:
        True si importado con éxito, False si hubo error o era duplicado.
    """
    print(f"\n📂 Procesando: {filepath.name}")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON inválido: {e}")
        return False
    except OSError as e:
        print(f"   ❌ Error al leer archivo: {e}")
        return False

    is_valid, error_msg = validate_session_json(data)
    if not is_valid:
        print(f"   ❌ Validación fallida: {error_msg}")
        return False

    session_id = insert_session(
        session_uuid=data["session_uuid"],
        session_date=data["session_date"],
        notes=data.get("notes", ""),
        source="pwa",
    )

    if session_id is None:
        return False

    imported = 0
    for i, s in enumerate(data["sets"]):
        try:
            insert_set(
                session_id=session_id,
                movement_name=s["movement"],
                weight_kg=float(s["weight_kg"]),
                reps=int(s["reps"]),
                set_order=s.get("set_order", i + 1),
                rpe=s.get("rpe"),
                notes=s.get("notes", ""),
            )
            imported += 1
        except Exception as e:
            print(f"   ⚠️  Set {i+1} ({s.get('movement', '?')}): {e}")

    print(f"   ✅ {imported}/{len(data['sets'])} sets importados "
          f"| ID={session_id} | {data['session_date']}")
    return True


# ─────────────────────────────────────────────────────────────
# WATCHDOG HANDLER
# ─────────────────────────────────────────────────────────────

class SessionFileHandler(FileSystemEventHandler):
    """
    Escucha eventos del sistema de archivos en la carpeta de iCloud.
    El set _recently_processed evita doble import cuando iCloud emite
    tanto on_created como on_modified al sincronizar.
    """

    def __init__(self):
        super().__init__()
        self._recently_processed: set[str] = set()

    def _should_process(self, path: str) -> bool:
        return bool(FILE_PATTERN.match(Path(path).name))

    def _process_if_new(self, path: str) -> None:
        """Procesa el archivo solo si no fue tocado en los últimos 5 segundos."""
        if path in self._recently_processed:
            return

        self._recently_processed.add(path)
        time.sleep(2.0)  # Esperar a que iCloud termine de escribir
        parse_and_import_session(Path(path))

        # Limpiar del set después de 5 s
        threading.Timer(5.0, lambda: self._recently_processed.discard(path)).start()

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            if self._should_process(event.src_path):
                self._process_if_new(event.src_path)

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            if self._should_process(event.src_path):
                self._process_if_new(event.src_path)


# ─────────────────────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────────────────────

def process_existing_files(folder: Path = SYNC_FOLDER) -> int:
    """
    Importa todos los JSON existentes en la carpeta (backfill).
    Útil para la primera ejecución o si el watcher estuvo apagado.
    """
    folder.mkdir(parents=True, exist_ok=True)
    files = sorted(folder.glob("liftlog_session_*.json"))

    if not files:
        print(f"📭 No hay archivos en {folder}")
        return 0

    print(f"📦 Procesando {len(files)} archivo(s) existente(s)...")
    count = sum(1 for f in files if parse_and_import_session(f))
    print(f"\n✅ Backfill completado: {count}/{len(files)} importados")
    return count


def start_watcher(folder: Path = SYNC_FOLDER) -> None:
    """
    Inicia el observer de watchdog. Bloquea hasta Ctrl+C.
    """
    folder.mkdir(parents=True, exist_ok=True)
    initialize_db()

    handler  = SessionFileHandler()
    observer = Observer()
    observer.schedule(handler, str(folder), recursive=False)
    observer.start()

    print(f"👁️  LiftLog Sync activo")
    print(f"   Carpeta: {folder}")
    print(f"   Patrón:  liftlog_session_*.json")
    print(f"   Ctrl+C para detener\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Sync detenido.")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LiftLog Sync Engine")
    parser.add_argument("--backfill", action="store_true",
                        help="Importar archivos existentes antes de iniciar el watcher")
    parser.add_argument("--folder", type=str, default=None,
                        help="Override de la carpeta monitoreada")
    args = parser.parse_args()

    watch_path = Path(args.folder).expanduser() if args.folder else SYNC_FOLDER

    if args.backfill:
        process_existing_files(watch_path)

    start_watcher(watch_path)