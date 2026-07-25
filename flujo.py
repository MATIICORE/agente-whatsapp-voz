#!/usr/bin/env python3
"""
El flujo completo, tal como pasaría en WhatsApp:

    llega una nota de voz  →  se transcribe (local, gratis)
                           →  el agente piensa y responde
                           →  se convierte en nota de voz
                           →  se manda de vuelta

Uso:
    python3 flujo.py audio.ogg          responde con voz
    python3 flujo.py audio.ogg --texto  responde solo con texto (más barato)
"""
import os, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import agente
import voz


def atender(ruta_audio, con_voz=True):
    t0 = time.time()
    gasto = 0.0

    # 1. Escuchar
    print("  🎧 escuchando…", end="", flush=True)
    texto, err = voz.escuchar(ruta_audio)
    if err:
        print(f"\n  ❌ {err}")
        return
    print(f"\r  🎧 Cliente dijo: «{texto}»")
    print("     (transcripción local, $0)\n")

    # 2. Pensar
    print("  🤔 pensando…", end="", flush=True)
    r = agente.responder(texto)
    respuesta, costo = r if isinstance(r, tuple) else (r, 0)
    gasto += costo
    limpio, marcas = agente.separar_marcas(respuesta)
    print(f"\r  💬 Agente: {limpio}")
    for m in marcas:
        print(f"     ⚙️  {m}")
    print(f"     (${costo:.1f})\n")

    # 3. Hablar
    if con_voz and limpio:
        print("  🎙️  grabando la respuesta…", end="", flush=True)
        salida = os.path.join("/tmp/agente-pruebas",
                              f"respuesta-{int(t0)}.mp3")
        os.makedirs(os.path.dirname(salida), exist_ok=True)
        ruta, c, err = voz.hablar(limpio, salida)
        if err:
            print(f"\r  ❌ {err}")
        else:
            gasto += c
            print(f"\r  🔊 Nota de voz lista: {ruta}")
            print(f"     (${c:.1f})\n")

    print(f"  ═══ {time.time() - t0:.1f} segundos · ${gasto:.1f} pesos en total ═══")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    atender(sys.argv[1], con_voz="--texto" not in sys.argv)
