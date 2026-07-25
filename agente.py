#!/usr/bin/env python3
"""
El cerebro del agente de WhatsApp.

Usa la API de Anthropic directamente. Sin librerías: solo urllib, así corre
en cualquier Mac sin instalar nada.

La llave va en un archivo .env al lado de este script:
    ANTHROPIC_API_KEY=sk-ant-...

Uso:
    python3 agente.py                  modo conversación
    python3 agente.py "tu pregunta"    una sola pregunta
"""
import json, os, sys, urllib.error, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
NEGOCIO = os.path.join(BASE, "negocio.json")
AGENDA = os.path.join(BASE, "agenda.json")

# Haiku sobra para esto y es el más barato: una conversación cuesta centavos.
MODELO = "claude-haiku-4-5-20251001"


def llave():
    """Lee la llave del .env. Nunca se escribe en el código."""
    k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(os.path.join(BASE, ".env"), encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith("ANTHROPIC_API_KEY"):
                    return linea.split("=", 1)[1].strip().strip("'\"")
    except FileNotFoundError:
        pass
    return None


def cargar(ruta, defecto=None):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return defecto


def pesos(n):
    return f"${n:,}".replace(",", ".")


def ficha_del_negocio(n):
    """La 'memoria' del agente: todo lo que sabe del negocio, en texto plano."""
    # la comuna solo se agrega si la dirección no la trae ya
    dir_completa = n["direccion"]
    if n["comuna"].lower() not in dir_completa.lower():
        dir_completa += f", {n['comuna']}"

    p = [f"NEGOCIO: {n['nombre']} — {dir_completa}",
         f"TELÉFONO: {n['telefono']}", "", "HORARIOS:"]
    for k, v in n["horarios"].items():
        p.append(f"  {k.replace('_', ' ')}: {v}")

    p += ["", "SERVICIOS Y PRECIOS:"]
    for s in n["servicios"]:
        p.append(f"  {s['nombre']}: {pesos(s['precio'])} ({s['duracion_min']} min)")

    p += ["", "LO QUE NO HACEMOS:"]
    p += [f"  - {x}" for x in n["no_hacemos"]]

    p += ["", "FORMAS DE PAGO: " + ", ".join(n["formas_de_pago"]), "", "REGLAS:"]
    p += [f"  - {x}" for x in n["reglas"]]

    p += ["", "PASAR A UNA PERSONA CUANDO:"]
    p += [f"  - {x}" for x in n["escalar_a_humano"]]
    return "\n".join(p)


def horas_libres(dia=None):
    """
    Las horas disponibles.

    Si el negocio tiene su Google Calendar configurado, se leen de ahí en vivo.
    Si no, cae al archivo agenda.json, que sirve para probar sin conectar nada.
    """
    negocio = cargar(NEGOCIO, {})
    if negocio.get("calendario_ical"):
        try:
            import agenda as _agenda
            reales, err = _agenda.libres()
            if reales and not err:
                return reales
        except Exception:
            pass  # si el calendario falla, mejor el archivo que quedarse sin nada

    a = cargar(AGENDA, {})
    return a.get(dia, []) if dia else a


def instrucciones(negocio):
    return f"""Eres quien contesta el WhatsApp de {negocio['nombre']}.
No eres un asistente de IA: eres la recepción de la veterinaria.

=== TODO LO QUE SABES ===
{ficha_del_negocio(negocio)}

=== HORAS DISPONIBLES ESTA SEMANA ===
{json.dumps(horas_libres(), ensure_ascii=False, indent=2)}

=== CÓMO ESCRIBES ===
- Español de Chile, natural, como escribe una persona por WhatsApp.
- Corto. Dos o tres líneas. Nadie lee párrafos en WhatsApp.
- 🔴 SIEMPRE DE USTED, en todo el mensaje, sin excepción.
  Nunca mezclar. Escribir "su mascota", "le acomoda", "¿necesita?".
  Nunca "tu mascota", "te acomoda", "¿necesitas?".
  Mezclar los dos tratos en el mismo mensaje se nota y suena a robot.
- 🔴 CERO EMOJIS. Ni uno, aunque la frase sea triste o simpática.
  Solo si la otra persona usó emojis primero, ahí puedes usar uno.
- Nunca digas que eres un bot ni un asistente virtual. Tampoco lo niegues si
  preguntan directo: en ese caso di que puedes ayudar con horas e información y
  que para lo demás pasas con alguien del equipo.

=== LAS TRES REGLAS QUE NO SE ROMPEN ===

1. SOLO DICES LO QUE ESTÁ ARRIBA.
   Si te preguntan un precio que no está en la lista, no lo inventas: dices que
   lo confirmas con el equipo. Un precio inventado le cuesta plata al negocio y
   la confianza al cliente.

2. NO DIAGNOSTICAS NUNCA.
   Si describen síntomas, no dices qué puede ser ni si es grave ni qué hacer.
   Ofreces una hora y, si suena urgente, pasas de inmediato con una persona.

3. TE RINDES RÁPIDO.
   Ante cualquier cosa de la lista "PASAR A UNA PERSONA", no improvisas.
   Dices que lo ve alguien del equipo al tiro y respondes:
   [ESCALAR: motivo en pocas palabras]
   Esa marca la lee el sistema, el cliente no la ve.

=== AGENDAR ===

🔴 ANTES DE DECIR QUE SÍ A UNA HORA, BÚSCALA EN LA LISTA DE ARRIBA.

Si el cliente pide una hora concreta ("el lunes a las 10"), tienes que revisar si
ese día y esa hora están en la lista de horas disponibles.

  · Está en la lista  → puedes confirmarla.
  · NO está           → esa hora YA ESTÁ TOMADA. Dilo y ofrece las más cercanas
                        que sí estén en la lista.

Ejemplo de cómo se responde cuando la hora no está libre:
  "El lunes a las 10 ya está tomada. Tengo a las 9:30 o a las 11:30, ¿le sirve alguna?"

**Confirmar una hora ocupada es el peor error que puedes cometer.** El cliente
llega a la clínica, hay otro animal en la mesa, y el negocio queda mal por tu culpa.
Ante la duda, ofrece horas de la lista en vez de aceptar la que te proponen.

Para agendar necesitas: qué servicio, para qué mascota, y qué día.
Cuando queden de acuerdo, cierras respondiendo:
[AGENDAR: servicio | día | hora | nombre de la mascota]
"""


def responder(mensaje, historial=None):
    negocio = cargar(NEGOCIO)
    if not negocio:
        return "❌ falta negocio.json"

    k = llave()
    if not k:
        return ("❌ falta la llave.\n"
                f"   Crea el archivo {os.path.join(BASE, '.env')} con esta línea:\n"
                "   ANTHROPIC_API_KEY=sk-ant-...")

    # El historial va como turnos de verdad, no pegado dentro del texto:
    # así el modelo distingue quién dijo qué.
    mensajes = []
    for q in (historial or []):
        mensajes.append({"role": "user" if q["de"] == "cliente" else "assistant",
                         "content": q["texto"]})
    mensajes.append({"role": "user", "content": mensaje})

    cuerpo = json.dumps({
        "model": MODELO,
        "max_tokens": 500,
        "system": instrucciones(negocio),
        "messages": mensajes,
    }).encode()

    pet = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=cuerpo,
        headers={"x-api-key": k, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})

    try:
        with urllib.request.urlopen(pet, timeout=60) as r:
            d = json.load(r)
        texto = "".join(b.get("text", "") for b in d.get("content", []))
        u = d.get("usage", {})
        # Haiku: US$1 por millón de tokens de entrada, US$5 de salida
        costo = (u.get("input_tokens", 0) / 1e6 * 1 + u.get("output_tokens", 0) / 1e6 * 5) * 950
        return texto.strip(), costo
    except urllib.error.HTTPError as e:
        detalle = e.read().decode()[:250]
        if e.code == 401:
            return "❌ la llave no es válida. Revisa el .env", 0
        if e.code == 400 and "credit" in detalle.lower():
            return "❌ sin saldo en la cuenta de Anthropic", 0
        return f"❌ error {e.code}: {detalle}", 0
    except Exception as e:
        return f"❌ {e}", 0


def separar_marcas(texto):
    """Aparta las marcas internas: el cliente nunca las ve."""
    limpio, marcas = [], []
    for linea in texto.split("\n"):
        s = linea.strip()
        (marcas if s.startswith(("[ESCALAR:", "[AGENDAR:")) else limpio).append(s)
    return "\n".join(limpio).strip(), marcas


def conversar():
    negocio = cargar(NEGOCIO)
    print(f"\n  💬 {negocio['nombre']} — modo prueba")
    print("  Escribe como si fueras un cliente. 'salir' para terminar.\n")
    historial, gasto = [], 0.0

    while True:
        try:
            msg = input("  Cliente: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg or msg.lower() in ("salir", "exit", "q"):
            break

        r = responder(msg, historial)
        texto, costo = r if isinstance(r, tuple) else (r, 0)
        gasto += costo
        limpio, marcas = separar_marcas(texto)

        print(f"\n  Agente: {limpio}\n")
        for m in marcas:
            print(f"    ⚙️  {m}")
        if costo:
            print(f"    💰 ${costo:.1f} este mensaje · ${gasto:.0f} la conversación\n")

        historial += [{"de": "cliente", "texto": msg},
                      {"de": "agente", "texto": limpio}]

    if gasto:
        print(f"  Total de la conversación: ${gasto:.0f} pesos\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        r = responder(" ".join(sys.argv[1:]))
        texto, costo = r if isinstance(r, tuple) else (r, 0)
        limpio, marcas = separar_marcas(texto)
        print(limpio)
        for m in marcas:
            print(f"  ⚙️  {m}")
        if costo:
            print(f"  💰 ${costo:.1f} pesos")
    else:
        conversar()
