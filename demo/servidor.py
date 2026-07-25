#!/usr/bin/env python3
"""
Servidor de la demo. Deja al agente detrás de una pantalla que se ve como WhatsApp,
para poder grabarlo y mostrárselo a un cliente.

    python3 demo/servidor.py     →  http://localhost:7500
"""
import json, os, sys, tempfile, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import agente
import voz

PUERTO = 7500
AUDIOS = os.path.join(tempfile.gettempdir(), "demo-agente")
os.makedirs(AUDIOS, exist_ok=True)

historial = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # sin ruido en la consola: se graba la pantalla, no el log

    # ── helpers ──────────────────────────────────────────────────────────────
    def _enviar(self, datos, tipo="application/json", codigo=200):
        cuerpo = datos if isinstance(datos, bytes) else json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _leer_cuerpo(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n) if n else b""

    # ── rutas ────────────────────────────────────────────────────────────────
    def do_GET(self):
        ruta = urllib.parse.urlparse(self.path).path

        if ruta in ("/", "/index.html"):
            with open(os.path.join(BASE, "demo", "index.html"), "rb") as f:
                return self._enviar(f.read(), "text/html; charset=utf-8")

        if ruta.startswith("/audio/"):
            f = os.path.join(AUDIOS, os.path.basename(ruta))
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    return self._enviar(fh.read(), "audio/mpeg")
            return self._enviar({"error": "no está"}, codigo=404)

        if ruta == "/negocio":
            with open(os.path.join(BASE, "negocio.json"), encoding="utf-8") as f:
                n = json.load(f)
            return self._enviar({"nombre": n["nombre"], "comuna": n["comuna"]})

        if ruta == "/reiniciar":
            historial.clear()
            return self._enviar({"ok": True})

        self._enviar({"error": "ruta desconocida"}, codigo=404)

    def do_POST(self):
        ruta = urllib.parse.urlparse(self.path).path

        # texto escrito
        if ruta == "/mensaje":
            d = json.loads(self._leer_cuerpo() or b"{}")
            return self._responder(d.get("texto", ""), d.get("con_voz", True))

        # nota de voz grabada en el navegador
        if ruta == "/nota":
            crudo = self._leer_cuerpo()
            tmp = os.path.join(AUDIOS, "entrada.webm")
            with open(tmp, "wb") as f:
                f.write(crudo)
            texto, err = voz.escuchar(tmp)
            if err:
                return self._enviar({"error": err}, codigo=500)
            return self._responder(texto, True, dijo=texto)

        self._enviar({"error": "ruta desconocida"}, codigo=404)

    # ── el trabajo de verdad ─────────────────────────────────────────────────
    def _responder(self, texto, con_voz, dijo=None):
        if not texto.strip():
            return self._enviar({"error": "mensaje vacío"}, codigo=400)

        r = agente.responder(texto, historial)
        respuesta, costo = r if isinstance(r, tuple) else (r, 0)
        limpio, marcas = agente.separar_marcas(respuesta)

        historial.append({"de": "cliente", "texto": texto})
        historial.append({"de": "agente", "texto": limpio})

        audio_url = None
        if con_voz and limpio:
            nombre = f"r{len(historial)}.mp3"
            ruta, c, err = voz.hablar(limpio, os.path.join(AUDIOS, nombre))
            if not err:
                audio_url = f"/audio/{nombre}"
                costo += c

        self._enviar({
            "dijo": dijo,          # lo que se entendió del audio del cliente
            "texto": limpio,
            "audio": audio_url,
            "marcas": marcas,
            "costo": round(costo, 1),
        })


if __name__ == "__main__":
    print(f"\n  Demo lista en  →  http://localhost:{PUERTO}\n")
    HTTPServer(("127.0.0.1", PUERTO), Handler).serve_forever()
