#!/bin/bash
# LiftLog — Script de arranque completo

cd "$(dirname "$0")"
source .venv/bin/activate

echo "🏋️ LiftLog iniciando..."
echo ""
# Backup automático de DB
BACKUP_DIR="data/backups"
mkdir -p "$BACKUP_DIR"
if [ -f "data/liftlog.db" ]; then
    cp "data/liftlog.db" "$BACKUP_DIR/liftlog_$(date +%Y-%m-%d).db"
    echo "💾 Backup creado: $BACKUP_DIR/liftlog_$(date +%Y-%m-%d).db"
fi
# Importar archivos pendientes
python src/sync.py --backfill

# Watcher en background
python src/sync.py &
SYNC_PID=$!

echo ""
echo "👁️  Watcher activo (PID: $SYNC_PID)"
echo "🌐 Abriendo dashboard..."
echo "   Ctrl+C para detener todo"
echo ""

# Dashboard
streamlit run app.py

# Al cerrar, detener watcher
kill $SYNC_PID 2>/dev/null
echo "🛑 LiftLog detenido."
