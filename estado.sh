#!/bin/bash
# ¿El agente está vivo? ¿En qué dirección? ¿Contesta de verdad?
#
# Se responde en 5 segundos y sin entrar a Meta. Pensado para preguntarlo desde
# el celular, estando lejos de la máquina donde corre el agente:
#
#     ssh <servidor> '~/agente-whatsapp/estado.sh'

cd "$(dirname "$0")" || exit 1
PUERTO="${WA_PUERTO:-7501}"
export PATH="$HOME/bin:$PATH"

echo ""
# Buscar solo "whatsapp.py". El proceso NO se llama "python3 whatsapp.py": macOS
# lo lanza como ".../Python.app/Contents/MacOS/Python whatsapp.py", con P
# mayúscula y ruta larga. Buscar "python3" daba CAÍDO con el agente vivo.
AGENTE=$(pgrep -f "whatsapp\.py" | head -1)
# Buscar solo "cloudflared tunnel". El túnel fijo corre como
# "cloudflared tunnel run agente-whatsapp", no como "--url http://...":
# con el patrón viejo esto daba TÚNEL CAÍDO con el túnel perfectamente vivo.
TUNEL=$(pgrep -f "cloudflared tunnel" | head -1)

if [ -n "$AGENTE" ]; then
  echo "  🟢 Agente arriba   · pid $AGENTE · hace $(ps -o etime= -p "$AGENTE" | tr -d ' ')"
else
  echo "  🔴 Agente CAÍDO"
fi

if [ -n "$TUNEL" ]; then
  echo "  🟢 Túnel arriba    · pid $TUNEL · hace $(ps -o etime= -p "$TUNEL" | tr -d ' ')"
else
  echo "  🔴 Túnel CAÍDO"
fi

# Dirección FIJA desde el 28-jul. Antes se leía de los logs porque cambiaba
# en cada arranque; ahora es siempre la misma y está en Meta una sola vez.
URL="https://wa.matiicore.com"
[ -n "$URL" ] && echo "  🔗 $URL"

# La prueba que importa: que un mensaje de Meta llegue hasta el agente. Que el
# proceso exista no alcanza, el túnel puede estar apuntando al vacío.
if [ -n "$URL" ]; then
  TOKEN=$(grep "^WA_VERIFY_TOKEN=" .env | cut -d= -f2-)
  R=$(curl -s -m 12 "$URL/webhook?hub.mode=subscribe&hub.verify_token=$TOKEN&hub.challenge=vivo")
  if [ "$R" = "vivo" ]; then
    echo "  ✅ Meta puede llegar hasta el agente"
  else
    echo "  ❌ La dirección NO llega al agente. Hay que actualizarla en Meta."
  fi
fi

# Cuántas conversaciones tiene abiertas ahora mismo.
python3 - <<'PY' 2>/dev/null
import json, os, time
ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else ".", "conversaciones.json")
try:
    d = json.load(open("conversaciones.json"))
except Exception:
    raise SystemExit
if not d:
    raise SystemExit
print(f"  💬 {len(d)} conversación(es) abierta(s):")
for k, v in d.items():
    h = (time.time() - v["visto"]) / 3600
    print(f"       ...{k[-4:]}  ·  {len(v['turnos'])} turnos  ·  hace {h:.1f} h")
PY

echo ""
