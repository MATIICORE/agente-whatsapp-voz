#!/bin/bash
# Levanta el agente y el túnel en ESTA máquina, con la dirección de siempre.
#
# Para qué sirve: el agente vivía en el Mac mini y el Mac mini se vendió. Mientras
# no haya VPS, esto lo revive donde estés, bajo demanda. La dirección sigue siendo
# https://wa.matiicore.com, así que NO hay que tocar nada en Meta.
#
#     ./revivir.sh            levantar
#     ./revivir.sh --bajar    apagar
#
# Se cae solo al cerrar el Mac. Eso está bien: es una solución de mientras tanto,
# no un servidor. Para que quede arriba de verdad hace falta el VPS.

cd "$(dirname "$0")" || exit 1
export PATH="$HOME/bin:$PATH"
# El nombre del archivo es el id del túnel. Se busca con glob a propósito: así el
# id no queda escrito en un repo público, y el script sirve si algún día cambia.
CRED=$(ls ~/.cloudflared/*.json 2>/dev/null | head -1)

# El proceso NO se llama "python3 whatsapp.py": macOS lo lanza como
# ".../Python.app/Contents/MacOS/Python whatsapp.py". Buscar solo "whatsapp.py".
bajar() {
  pkill -f "whatsapp\.py"          2>/dev/null && echo "  agente abajo"
  pkill -f "cloudflared tunnel run" 2>/dev/null && echo "  túnel abajo"
}

if [ "$1" = "--bajar" ]; then
  echo ""; bajar; echo ""; exit 0
fi

# Las credenciales del túnel viven fuera del repo (son secretas). Si esta máquina
# no las tiene, se copian del respaldo.
if [ ! -f "$CRED" ]; then
  RESP=~/Claude/_respaldo-macmini-final-20260803/.cloudflared
  if [ -d "$RESP" ]; then
    mkdir -p ~/.cloudflared
    cp "$RESP"/*.json "$RESP"/cert.pem "$RESP"/config.yml ~/.cloudflared/
    chmod 600 ~/.cloudflared/*.json ~/.cloudflared/cert.pem
    echo "  credenciales del túnel restauradas desde el respaldo"
  else
    echo "  ❌ No están las credenciales del túnel ni el respaldo."
    echo "     Sin ellas el túnel no puede levantar wa.matiicore.com."
    exit 1
  fi
fi

echo ""
if pgrep -qf "whatsapp\.py"; then
  echo "  🟢 El agente ya estaba arriba"
else
  nohup python3 whatsapp.py > /tmp/wa-agente.log 2>&1 &
  sleep 3
  pgrep -qf "whatsapp\.py" && echo "  🟢 Agente arriba" \
    || { echo "  ❌ El agente no arrancó:"; tail -12 /tmp/wa-agente.log; exit 1; }
fi

if pgrep -qf "cloudflared tunnel run"; then
  echo "  🟢 El túnel ya estaba arriba"
else
  nohup cloudflared tunnel run agente-whatsapp > /tmp/wa-tunel.log 2>&1 &
  # Esperar a que registre al menos una conexión, no a que pase un tiempo fijo.
  # En redes que bloquean QUIC cae solo a http2 y tarda un poco más.
  for _ in $(seq 1 20); do
    grep -q "Registered tunnel connection" /tmp/wa-tunel.log 2>/dev/null && break
    sleep 2
  done
  grep -q "Registered tunnel connection" /tmp/wa-tunel.log \
    && echo "  🟢 Túnel arriba" \
    || { echo "  ⚠️  El túnel no registró conexión. Log en /tmp/wa-tunel.log"; }
fi

echo ""
./estado.sh
