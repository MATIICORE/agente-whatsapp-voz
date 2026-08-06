#!/usr/bin/env python3
"""
El cable que enchufa el agente a WhatsApp de verdad.

Hasta ahora el agente vivía en la terminal y en una demo que imitaba WhatsApp.
Esto lo conecta a la Cloud API oficial de Meta: llega un mensaje real de un
cliente, contesta el agente, y la respuesta le llega al celular.

    Meta  --POST-->  este servidor  -->  agente.responder()  --POST-->  Meta

Sin librerías, igual que el resto del proyecto: solo la librería estándar.

Uso:
    python3 whatsapp.py           # escucha en el 7501
    python3 whatsapp.py --probar  # revisa la configuración sin levantar nada

Antes hay que llenar en el .env:
    WA_TOKEN            token de la app de Meta
    WA_PHONE_ID         id del número emisor (lo da Meta, no es el número)
    WA_VERIFY_TOKEN     una palabra cualquiera que tú inventas
    WA_APP_SECRET       el secreto de la app, para verificar que Meta es Meta
"""
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import agente

PUERTO = int(os.environ.get("WA_PUERTO", "7501"))
API = "https://graph.facebook.com/v21.0"
FFMPEG = os.path.expanduser("~/bin/ffmpeg")

# ── Memoria de las conversaciones ────────────────────────────────────────────
#
# 🔴 Esto vivía SOLO en memoria y fue un error. Al reiniciar el proceso para
# actualizar el código, un cliente que estaba conversando tuvo que repetir lo
# que ya había dicho, y el agente le preguntó dos veces la misma cosa. Un
# reinicio del Mac mini haría lo mismo.
#
# Ahora va a disco. Se conserva 24 h, que es exactamente lo que dura la ventana
# de WhatsApp: pasado ese rato la conversación ya no se puede continuar de todas
# formas, así que guardar más tiempo sería acumular datos de clientes sin motivo.
CHARLAS_JSON = os.path.join(BASE, "conversaciones.json")
VENCE = 24 * 3600
LIMITE_HISTORIAL = 12   # 6 idas y vueltas; más que eso encarece cada mensaje

VISTOS = set()          # ids ya procesados: Meta reenvía si tardas en responder
_LOCK = threading.Lock()
_LOCKS_POR_NUMERO = {}


def lock_de(numero):
    """
    Un candado por cliente.

    Sin esto, dos mensajes seguidos del mismo número se procesan en paralelo:
    los dos leen el historial viejo y el segundo en terminar pisa lo que
    escribió el primero. Con notas de voz es casi seguro que pase, porque cada
    una tarda 6-8 segundos entre transcribir, pensar y hablar.
    """
    with _LOCK:
        return _LOCKS_POR_NUMERO.setdefault(numero, threading.Lock())


def cargar_charlas():
    try:
        with open(CHARLAS_JSON, encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    ahora = time.time()
    return {n: c for n, c in d.items() if ahora - c.get("visto", 0) < VENCE}


def guardar_charla(numero, historial):
    with _LOCK:
        d = cargar_charlas()
        d[numero] = {"visto": time.time(), "turnos": historial}
        tmp = CHARLAS_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, CHARLAS_JSON)   # atómico: nunca queda a medio escribir


def historial_de(numero):
    return cargar_charlas().get(numero, {}).get("turnos", [])


def config(nombre, defecto=""):
    """Lee del entorno o del .env, igual que agente.llave()."""
    v = os.environ.get(nombre, "").strip()
    if v:
        return v
    try:
        with open(os.path.join(BASE, ".env"), encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith(nombre):
                    return linea.split("=", 1)[1].strip().strip("'\"")
    except FileNotFoundError:
        pass
    return defecto


def pedir(url, datos=None, cabeceras=None, timeout=30):
    cab = {"Authorization": f"Bearer {config('WA_TOKEN')}"}
    cab.update(cabeceras or {})
    cuerpo = None
    if datos is not None:
        cuerpo = json.dumps(datos).encode()
        cab["Content-Type"] = "application/json"
    pet = urllib.request.Request(url, data=cuerpo, headers=cab)
    with urllib.request.urlopen(pet, timeout=timeout) as r:
        crudo = r.read()
        try:
            return json.loads(crudo), None
        except json.JSONDecodeError:
            return crudo, None


def enviar(numero, texto):
    """Manda un mensaje de texto. Gratis: va dentro de la ventana de 24 h."""
    try:
        r, _ = pedir(f"{API}/{config('WA_PHONE_ID')}/messages", {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {"preview_url": False, "body": texto},
        })
        return True, None
    except urllib.error.HTTPError as e:
        return False, f"{e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return False, str(e)


def subir_audio(ruta_mp3):
    """
    Sube una nota de voz a Meta y devuelve su id.

    WhatsApp solo la muestra como nota de voz (con la onda y el play) si va en
    ogg/opus. Si se manda el mp3 tal cual, llega como archivo adjunto y el
    cliente tiene que descargarlo: pierde toda la gracia.
    """
    ogg = ruta_mp3.rsplit(".", 1)[0] + ".ogg"
    r = subprocess.run([FFMPEG, "-nostdin", "-y", "-i", ruta_mp3,
                        "-c:a", "libopus", "-b:a", "32k", "-ar", "48000",
                        "-ac", "1", ogg],
                       capture_output=True, timeout=120)
    if not os.path.exists(ogg) or os.path.getsize(ogg) == 0:
        return None, "ffmpeg no pudo convertir el audio"

    # multipart/form-data a mano: el resto del proyecto no usa librerías y esta
    # no es razón suficiente para empezar.
    lim = "----matiicore" + str(os.getpid())
    with open(ogg, "rb") as f:
        datos = f.read()
    cuerpo = b""
    for campo, valor in [("messaging_product", "whatsapp"), ("type", "audio/ogg")]:
        cuerpo += (f"--{lim}\r\nContent-Disposition: form-data; name=\"{campo}\"\r\n\r\n"
                   f"{valor}\r\n").encode()
    cuerpo += (f"--{lim}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"voz.ogg\"\r\nContent-Type: audio/ogg\r\n\r\n").encode()
    cuerpo += datos + f"\r\n--{lim}--\r\n".encode()

    pet = urllib.request.Request(
        f"{API}/{config('WA_PHONE_ID')}/media", data=cuerpo,
        headers={"Authorization": f"Bearer {config('WA_TOKEN')}",
                 "Content-Type": f"multipart/form-data; boundary={lim}"})
    try:
        with urllib.request.urlopen(pet, timeout=90) as r:
            return json.load(r).get("id"), None
    except urllib.error.HTTPError as e:
        return None, f"{e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)


def enviar_voz(numero, texto):
    """Convierte la respuesta en nota de voz y la manda. Devuelve el costo."""
    import voz
    mp3 = f"/tmp/wa-resp-{numero}.mp3"
    ruta, costo, err = voz.hablar(texto, mp3)
    if err:
        return 0, err

    media_id, err = subir_audio(ruta)
    if err:
        return costo, err

    try:
        pedir(f"{API}/{config('WA_PHONE_ID')}/messages", {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "audio",
            "audio": {"id": media_id},
        })
        return costo, None
    except urllib.error.HTTPError as e:
        return costo, f"{e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return costo, str(e)


def bajar_audio(media_id):
    """
    Baja una nota de voz. Son dos pasos: primero Meta da una URL temporal,
    después se descarga con el mismo token.
    """
    try:
        info, _ = pedir(f"{API}/{media_id}")
        url = info.get("url")
        if not url:
            return None, "Meta no devolvió la URL del audio"
        pet = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {config('WA_TOKEN')}"})
        with urllib.request.urlopen(pet, timeout=60) as r:
            crudo = r.read()
        ruta = f"/tmp/wa-{media_id}.ogg"
        with open(ruta, "wb") as f:
            f.write(crudo)
        return ruta, None
    except Exception as e:
        return None, str(e)


def firma_valida(cuerpo, cabecera):
    """
    Comprueba que el POST venga de Meta y no de cualquiera.

    Sin esto, el webhook es una puerta abierta: quien sepa la URL puede
    inyectar mensajes falsos y gastar la API de Anthropic del negocio.
    """
    secreto = config("WA_APP_SECRET")
    if not secreto:
        return False, "falta WA_APP_SECRET en el .env"
    if not cabecera or not cabecera.startswith("sha256="):
        return False, "el POST no trae firma"
    esperado = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado, cabecera[7:]):
        return False, "la firma no cuadra"
    return True, None


def atender(numero, texto, nombre="", con_voz=False):
    """
    Piensa la respuesta y la manda. Corre en su propio hilo.

    `con_voz` responde en el mismo formato en que le hablaron: si el cliente
    mandó una nota de voz, se le contesta con nota de voz. Escribir de vuelta a
    quien te habló se siente como que no te escucharon.
    """
    t0 = time.time()
    # El candado se toma ANTES de leer el historial y se suelta después de
    # guardarlo. Así dos mensajes seguidos del mismo cliente se atienden en
    # orden y el segundo ve lo que respondió el primero.
    candado = lock_de(numero)
    candado.acquire()

    historial = historial_de(numero)

    r = agente.responder(texto, historial)
    respuesta, costo = r if isinstance(r, tuple) else (r, 0)
    limpio, marcas = agente.separar_marcas(respuesta)

    modo = "texto"
    if limpio:
        if con_voz:
            c, err = enviar_voz(numero, limpio)
            costo += c
            if err:
                # Si la voz falla, va el texto igual: mejor una respuesta
                # escrita que ninguna respuesta.
                print(f"  ⚠️  la voz falló ({err}), mando texto")
                enviar(numero, limpio)
            else:
                modo = "voz"
        if modo == "texto":
            ok, err = enviar(numero, limpio)
            if not ok:
                print(f"  ❌ no se pudo enviar: {err}")

    guardar_charla(numero, (historial + [{"de": "cliente", "texto": texto},
                                         {"de": "agente", "texto": limpio}])[-LIMITE_HISTORIAL:])
    candado.release()

    print(f"  💬 {nombre or numero}: «{texto[:60]}»")
    print(f"  {'🔊' if modo == 'voz' else '🤖'} {limpio[:80]}")
    for m in marcas:
        # Lo importante del día: acá es donde el negocio tiene que mirar.
        print(f"  🚩 {m}")
    print(f"     ${costo:.1f} · {time.time() - t0:.1f}s · por {modo}\n")


class Manejador(BaseHTTPRequestHandler):

    def log_message(self, *a):
        pass  # el log propio ya dice lo que importa

    def responder_seco(self, codigo, cuerpo=b""):
        self.send_response(codigo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        if cuerpo:
            self.wfile.write(cuerpo)

    def do_GET(self):
        """Meta llama acá una sola vez, para comprobar que el webhook existe."""
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        modo = q.get("hub.mode", [""])[0]
        token = q.get("hub.verify_token", [""])[0]
        reto = q.get("hub.challenge", [""])[0]

        if modo == "subscribe" and token == config("WA_VERIFY_TOKEN"):
            print("  ✅ Meta verificó el webhook")
            return self.responder_seco(200, reto.encode())

        print("  ⚠️  alguien pidió verificar con un token que no es el nuestro")
        self.responder_seco(403)

    def do_POST(self):
        crudo = self.rfile.read(int(self.headers.get("Content-Length", 0)))

        ok, err = firma_valida(crudo, self.headers.get("X-Hub-Signature-256", ""))
        if not ok:
            print(f"  🚫 POST rechazado ({err})")
            return self.responder_seco(403)

        # Se contesta 200 de inmediato. Si tardas, Meta cree que fallaste y
        # reenvía el mismo mensaje una y otra vez.
        self.responder_seco(200)

        try:
            datos = json.loads(crudo)
        except json.JSONDecodeError:
            return

        for entrada in datos.get("entry", []):
            for cambio in entrada.get("changes", []):
                valor = cambio.get("value", {})
                perfiles = {c["wa_id"]: c.get("profile", {}).get("name", "")
                            for c in valor.get("contacts", [])}

                for m in valor.get("messages", []):
                    if m["id"] in VISTOS:
                        continue
                    VISTOS.add(m["id"])

                    numero = m["from"]
                    nombre = perfiles.get(numero, "")
                    tipo = m.get("type")

                    era_voz = False
                    if tipo == "text":
                        texto = m["text"]["body"]
                    elif tipo == "audio":
                        ruta, e = bajar_audio(m["audio"]["id"])
                        if e:
                            print(f"  ❌ audio: {e}")
                            continue
                        import voz
                        texto, e = voz.escuchar(ruta)   # Whisper local, $0
                        if e:
                            print(f"  ❌ transcripción: {e}")
                            continue
                        era_voz = True
                        print(f"  🎧 nota de voz transcrita")
                    else:
                        enviar(numero, "Por acá puedo leer texto y notas de voz. "
                                       "¿Me lo escribe?")
                        continue

                    threading.Thread(target=atender,
                                     args=(numero, texto, nombre, era_voz),
                                     daemon=True).start()


def revisar():
    """Dice qué falta antes de levantar nada."""
    print("\n  Revisión de configuración\n")
    faltan = []
    for k, q in [("ANTHROPIC_API_KEY", "el cerebro del agente"),
                 ("WA_TOKEN", "token de la app de Meta"),
                 ("WA_PHONE_ID", "id del número emisor"),
                 ("WA_VERIFY_TOKEN", "palabra que tú inventas"),
                 ("WA_APP_SECRET", "secreto de la app, verifica que Meta es Meta")]:
        v = config(k) or (agente.llave() if k == "ANTHROPIC_API_KEY" else "")
        print(f"   {'✅' if v else '❌'}  {k:<20} {q}")
        if not v:
            faltan.append(k)

    n = agente.cargar(os.path.join(BASE, "negocio.json"), {})
    print(f"\n   {'✅' if n else '❌'}  negocio.json          {n.get('nombre', 'no se pudo leer')}")

    if faltan:
        print(f"\n  Falta llenar en .env: {', '.join(faltan)}")
        print("  Los pasos están en CONECTAR-WHATSAPP.md\n")
    else:
        print("\n  Todo listo. Levántalo con:  python3 whatsapp.py\n")
    return not faltan


if __name__ == "__main__":
    # Sin esto, si mandas la salida a un archivo (`python3 whatsapp.py > log`),
    # Python la va guardando en un buffer y el archivo se ve vacío. Al cortar el
    # proceso con Ctrl+C se pierde entera. Un servidor tiene que escribir línea
    # a línea o no sirve para mirar qué está pasando.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if "--probar" in sys.argv:
        sys.exit(0 if revisar() else 1)

    if not revisar():
        sys.exit(1)

    print(f"\n  🟢 Escuchando en http://localhost:{PUERTO}")
    print("     Falta exponerlo a internet para que Meta llegue.")
    print("     Ver CONECTAR-WHATSAPP.md, paso 5.\n")
    try:
        HTTPServer(("0.0.0.0", PUERTO), Manejador).serve_forever()
    except KeyboardInterrupt:
        print("\n  Cerrado.\n")
