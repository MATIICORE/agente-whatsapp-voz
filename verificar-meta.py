#!/usr/bin/env python3
"""
Comprueba las llaves de Meta ANTES de configurar nada.

Sin esto, un token mal copiado (un espacio de más, un carácter cortado) se
descubre recién cuando el webhook ya está montado y no llega ningún mensaje.
Ahí no se sabe si falla el token, el id, el túnel o el código.

Uso:
    python3 verificar-meta.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
API = "https://graph.facebook.com/v21.0"


def config(nombre):
    v = os.environ.get(nombre, "").strip()
    if v:
        return v
    try:
        with open(os.path.join(BASE, ".env"), encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith(nombre + "="):
                    return linea.split("=", 1)[1].strip().strip("'\"")
    except FileNotFoundError:
        pass
    return ""


def consultar(ruta, token):
    pet = urllib.request.Request(f"{API}/{ruta}",
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(pet, timeout=20) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode())
            return None, d.get("error", {}).get("message", str(e))
        except Exception:
            return None, f"HTTP {e.code}"
    except Exception as e:
        return None, str(e)


def main():
    token = config("WA_TOKEN")
    phone = config("WA_PHONE_ID")
    secreto = config("WA_APP_SECRET")

    print()
    fallos = []

    # ── 1. Las tres están puestas ──
    for nombre, valor in [("WA_TOKEN", token), ("WA_PHONE_ID", phone),
                          ("WA_APP_SECRET", secreto)]:
        if not valor:
            print(f"  ❌ {nombre} está vacío")
            fallos.append(nombre)
    if fallos:
        print("\n  Faltan llaves en el .env. Los pasos: CONECTAR-WHATSAPP.md\n")
        return 1

    # ── 2. Errores de copiado que se ven a simple vista ──
    if " " in token or "\n" in token:
        print("  ⚠️  el token trae espacios. Suele pasar al copiar de la pantalla de Meta")
    if not token.startswith("EAA"):
        print(f"  ⚠️  el token no empieza en EAA (empieza en '{token[:6]}'). Revisa que sea el correcto")
    if not phone.isdigit():
        print(f"  ❌ WA_PHONE_ID debería ser solo números, y es '{phone[:24]}'")
        print("     Ojo: NO es el número de teléfono, es el identificador que da Meta")
        fallos.append("WA_PHONE_ID")

    # ── 3. Contra la API de verdad ──
    print("  Preguntándole a Meta…\n")

    d, err = consultar(f"{phone}?fields=display_phone_number,verified_name,quality_rating", token)
    if err:
        print(f"  ❌ no se pudo leer el número: {err}")
        if "expired" in err.lower() or "session" in err.lower():
            print("     El token temporal dura 24 horas. Genera otro en la consola de Meta.")
        fallos.append("conexión")
    else:
        print(f"  ✅ Número     : {d.get('display_phone_number', '?')}")
        print(f"  ✅ A nombre de: {d.get('verified_name', '?')}")
        if d.get("quality_rating"):
            print(f"     Calidad    : {d['quality_rating']}")

    # ── 4. Cuándo se vence el token ──
    d2, err2 = consultar(f"debug_token?input_token={token}", token)
    if not err2 and d2.get("data"):
        info = d2["data"]
        exp = info.get("expires_at", 0)
        if exp == 0:
            print("  ✅ Token     : permanente, no se vence")
        else:
            import datetime
            cuando = datetime.datetime.fromtimestamp(exp)
            print(f"  ⏳ Token     : se vence el {cuando:%d-%b %H:%M}")
            print("     Es el temporal. Para producción hay que crear un usuario del sistema.")

    print()
    if fallos:
        print("  Hay algo mal. Revísalo antes de seguir con el webhook.\n")
        return 1

    print("  Todo correcto. Ahora:  ./arrancar.sh\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
