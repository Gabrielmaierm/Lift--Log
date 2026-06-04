#!/bin/bash
# LiftLog — Script de arranque completo
# Doble clic en Finder o ejecutar con: ./start.sh

cd "$(dirname "$0")"
source .venv/bin/activate

echo "🏋️ LiftLog iniciando..."
echo "   Watcher: monitoreando iCloud Drive"
echo "   Dashboard: abriendo en navegador"
echo ""
echo "   Para detener: Ctrl+C"
echo ""

# Importar archivos pendientes antes de iniciar
python src/sync.py --backfill

# Watcher en background
python src/sync.py &
SYNC_PID=$!

# Dashboard (bloquea hasta que el usuario lo cierre)
streamlit run app.py

# Al cerrar el dashboard, detener el watcher
kill $SYNC_PID 2>/dev/null
echo ""
echo "🛑 LiftLog detenido."
