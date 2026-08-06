#!/bin/bash
# Levanta el agente y el tunel de una sola vez, y deja a la vista la direccion
# que hay que pegar en Meta.
#
# Sin esto son dos terminales, buscar la URL entre el ruido de cloudflared y
# copiarla a mano. Se corta todo con Ctrl+C.

cd "$(dirname "$0")" || exit 1
PUERTO="${WA_PUERTO:-7501}"

# Si ya hay uno arriba, no levantar otro. Sin este control el agente nuevo
# muere solo porque el puerto está ocupado, y el script decía "el agente no
# arrancó": justo lo contrario de lo que pasa. Se pierde media hora buscando
# una caída que no existe.
VIEJO=$(pgrep -f "whatsapp\.py" | head -1)
if [ -n "$VIEJO" ]; then
  echo ""
  echo "  ✅ El agente YA está corriendo (pid $VIEJO). No se toca."
  URL=$(grep -hoE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/tunel-whatsapp.log /tmp/wa-mini.log 2>/dev/null | tail -1)
  if [ -n "$URL" ]; then
    echo "     Su dirección: $URL"
  fi
  echo ""
  echo "     Para reiniciarlo de cero:  ./arrancar.sh --reiniciar"
  echo ""
  [ "$1" != "--reiniciar" ] && exit 0
  echo "  Cerrando el anterior…"
  pkill -f "whatsapp\.py"
  pkill -f "cloudflared tunnel --url http://localhost:$PUERTO"
  sleep 2
fi

echo ""
echo "  Revisando la configuración…"
if ! python3 whatsapp.py --probar; then
  exit 1
fi

# El agente primero. Si no levanta, no tiene sentido abrir el tunel.
python3 whatsapp.py &
AGENTE=$!
sleep 2

if ! kill -0 "$AGENTE" 2>/dev/null; then
  echo "  ❌ el agente no arrancó"
  exit 1
fi

# La salida de cloudflared se guarda para poder pescar la direccion: la imprime
# una sola vez, entre varias lineas de ruido.
LOG="/tmp/tunel-whatsapp.log"
: > "$LOG"
cloudflared tunnel --url "http://localhost:$PUERTO" > "$LOG" 2>&1 &
TUNEL=$!

limpiar() {
  echo ""
  echo "  Cerrando…"
  kill "$AGENTE" "$TUNEL" 2>/dev/null
  exit 0
}
trap limpiar SIGINT SIGTERM

echo "  Abriendo el túnel…"
URL=""
for _ in $(seq 1 30); do
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG" | head -1)
  [ -n "$URL" ] && break
  sleep 1
done

if [ -z "$URL" ]; then
  echo "  ❌ el túnel no dio dirección. Mira $LOG"
  limpiar
fi

VERIFY=$(grep "^WA_VERIFY_TOKEN=" .env | cut -d= -f2-)

echo ""
echo "  ════════════════════════════════════════════════════════════"
echo "   PEGAR ESTO EN META"
echo "   (WhatsApp → Configuración → Webhooks → Editar)"
echo ""
echo "   URL de devolución de llamada:"
echo "   $URL"
echo ""
echo "   Token de verificación:"
echo "   $VERIFY"
echo ""
echo "   Después, en Campos del webhook, suscribirse a: messages"
echo "  ════════════════════════════════════════════════════════════"
echo ""
echo "   ⚠️  Esta dirección cambia cada vez que arrancas. Hay que"
echo "       actualizarla en Meta en cada arranque."
echo ""
echo "   Ctrl+C corta el agente y el túnel."
echo ""

wait "$AGENTE"
