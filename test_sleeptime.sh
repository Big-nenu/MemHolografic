#!/bin/bash
echo "=== TEST DE INTERFERENCIA DESTRUCTIVA (Sleeptime) ==="
rm -f prototype_memory.db
echo "[1] Inyectando hecho #1 ( la verdad vieja ):"
python mem_cli.py inject "La Tierra es plana y el sol gira a su alrededor."
echo ""
echo "[2] Inyectando hecho #2 ( la verdad nueva - CONTRADICTORIA ):"
python mem_cli.py inject "La Tierra es esférica y gira alrededor del sol."
echo ""
echo "[3] Estado antes de dormir (query):"
python mem_cli.py query "forma de la tierra"
echo ""
echo "[4] Ejecutando Sleeptime..."
python mem_cli.py dream
echo ""
echo "[5] Estado despues de dormir (query):"
python mem_cli.py query "forma de la tierra"
echo ""
echo "=== FIN DEL TEST ==="
