#!/usr/bin/env python3
"""
Oído y voz del agente.

  escuchar(audio)  →  el cliente manda una nota de voz, la convertimos a texto
  hablar(texto)    →  el agente responde con una nota de voz

La transcripción corre LOCAL con Whisper: no cuesta nada y el audio del cliente
no sale del computador. La voz sí usa ElevenLabs, que se paga por caracteres.

Uso suelto:
    python3 voz.py escuchar audio.ogg
    python3 voz.py hablar "hola, buenas tardes"
"""
import json, os, subprocess, sys, tempfile, urllib.error, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
WHISPER_PY = os.path.expanduser("~/Claude/4-herramientas/transcribir/.venv/bin/python")
FFMPEG = os.path.expanduser("~/bin/ffmpeg")
MODELO_WHISPER = "mlx-community/whisper-large-v3-turbo"


def _env(clave, *rutas):
    v = os.environ.get(clave, "").strip()
    if v:
        return v
    for r in (os.path.join(BASE, ".env"), *rutas):
        try:
            with open(os.path.expanduser(r), encoding="utf-8") as f:
                for linea in f:
                    if linea.strip().startswith(clave):
                        return linea.split("=", 1)[1].strip().strip("'\"")
        except FileNotFoundError:
            continue
    return None


# ── OÍDO ─────────────────────────────────────────────────────────────────────

def escuchar(ruta_audio):
    """Nota de voz -> texto. Corre local, no cuesta nada."""
    if not os.path.exists(ruta_audio):
        return None, f"no existe el archivo {ruta_audio}"
    if not os.path.exists(WHISPER_PY):
        return None, "falta Whisper (~/Claude/4-herramientas/transcribir/)"

    # WhatsApp manda .ogg/opus. Whisper trabaja mejor con wav 16 kHz mono.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
        wav = t.name
    try:
        subprocess.run([FFMPEG, "-nostdin", "-y", "-i", ruta_audio,
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav],
                       capture_output=True, timeout=120)

        codigo = (
            "import mlx_whisper, json, sys;"
            f"r = mlx_whisper.transcribe({wav!r}, path_or_hf_repo={MODELO_WHISPER!r},"
            " language='es', verbose=False);"
            "print(json.dumps({'texto': r['text'].strip()}, ensure_ascii=False))"
        )
        p = subprocess.run([WHISPER_PY, "-c", codigo],
                           capture_output=True, text=True, timeout=300)
        for linea in reversed(p.stdout.strip().split("\n")):
            if linea.startswith("{"):
                return json.loads(linea)["texto"], None
        return None, (p.stderr or "Whisper no devolvió nada")[:200]
    except subprocess.TimeoutExpired:
        return None, "la transcripción se demoró demasiado"
    finally:
        os.unlink(wav) if os.path.exists(wav) else None


# ── VOZ ──────────────────────────────────────────────────────────────────────

def hablar(texto, salida=None, voz_id=None):
    """Texto -> nota de voz. Devuelve (ruta, costo_en_pesos, error)."""
    k = _env("ELEVENLABS_API_KEY", "~/Claude/4-herramientas/remotion-video/.env")
    if not k:
        return None, 0, "falta ELEVENLABS_API_KEY"

    # Por defecto, la voz configurada para el negocio
    if not voz_id:
        try:
            with open(os.path.join(BASE, "negocio.json"), encoding="utf-8") as f:
                voz_id = json.load(f).get("voz_id")
        except Exception:
            pass
    voz_id = voz_id or "6F5Zhi321D3Oq7v1oNT4"

    salida = salida or os.path.join(tempfile.gettempdir(), "respuesta.mp3")
    cuerpo = json.dumps({
        "text": texto,
        "model_id": "eleven_multilingual_v2",   # el que maneja bien el español
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode()

    pet = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz_id}",
        data=cuerpo,
        headers={"xi-api-key": k, "content-type": "application/json"})

    try:
        with urllib.request.urlopen(pet, timeout=90) as r:
            audio = r.read()
        with open(salida, "wb") as f:
            f.write(audio)
        # ElevenLabs cobra por carácter: ~US$50 por millón en los planes de pago
        costo = len(texto) / 1e6 * 50 * 950
        return salida, costo, None
    except urllib.error.HTTPError as e:
        return None, 0, f"error {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, 0, str(e)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "escuchar":
        texto, err = escuchar(sys.argv[2])
        print(f"❌ {err}" if err else f"📝 {texto}")

    elif sys.argv[1] == "hablar":
        ruta, costo, err = hablar(" ".join(sys.argv[2:]))
        print(f"❌ {err}" if err else f"🔊 {ruta}   (${costo:.1f} pesos)")
