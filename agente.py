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
import json, os, re, sys, urllib.error, urllib.request

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
    """La 'memoria' del agente: todo lo que sabe del negocio, en texto plano.

    Todo campo se lee con .get(). NINGÚN negocio tiene la misma ficha: una
    veterinaria cobra por consulta de 30 minutos y un gimnasio vende planes
    mensuales sin duración. Antes esto reventaba con KeyError ante un campo
    ausente y el agente NO RESPONDÍA NADA: el cliente ve silencio, no un error.
    Un campo que falta ahora simplemente no se escribe en la ficha.
    """
    dir_completa = n.get("direccion", "")
    comuna = n.get("comuna", "")
    # la comuna solo se agrega si la dirección no la trae ya
    if comuna and comuna.lower() not in dir_completa.lower():
        dir_completa = f"{dir_completa}, {comuna}".strip(", ")

    p = [f"NEGOCIO: {n.get('nombre', '')}" + (f" — {dir_completa}" if dir_completa else "")]
    if n.get("telefono"):
        p.append(f"TELÉFONO: {n['telefono']}")

    if n.get("horarios"):
        p += ["", "HORARIOS:"]
        for k, v in n["horarios"].items():
            p.append(f"  {k.replace('_', ' ')}: {v}")

    if n.get("servicios"):
        p += ["", "SERVICIOS Y PRECIOS:"]
        for s in n["servicios"]:
            linea = f"  {s.get('nombre', '')}"
            # precio None = "se cotiza": decirlo es mejor que callarlo, porque
            # es justo el caso en que el agente tiene que derivar a una persona.
            linea += f": {pesos(s['precio'])}" if s.get("precio") else ": a convenir"
            if s.get("duracion_min"):
                linea += f" ({s['duracion_min']} min)"
            if s.get("detalle"):
                linea += f" — {s['detalle']}"
            p.append(linea)

    for clave, titulo in (("no_hacemos", "LO QUE NO HACEMOS:"),
                          ("reglas", "REGLAS:"),
                          ("escalar_a_humano", "PASAR A UNA PERSONA CUANDO:")):
        if n.get(clave):
            p += ["", titulo] + [f"  - {x}" for x in n[clave]]

    if n.get("formas_de_pago"):
        p += ["", "FORMAS DE PAGO: " + ", ".join(n["formas_de_pago"])]

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
No eres un asistente de IA: eres la recepción de este negocio.

=== TODO LO QUE SABES ===
{ficha_del_negocio(negocio)}

=== HORAS DISPONIBLES ESTA SEMANA ===
{json.dumps(horas_libres(), ensure_ascii=False, indent=2)}

=== CÓMO ESCRIBES ===
- Español de Chile, natural, como escribe una persona por WhatsApp.
- Corto. Dos o tres líneas. Nadie lee párrafos en WhatsApp.
- 🔴 SIEMPRE DE USTED, en todo el mensaje, sin excepción.
  Nunca mezclar. Escribir "le acomoda", "¿necesita?", "su consulta".
  Nunca "te acomoda", "¿necesitas?", "tu consulta".
  Mezclar los dos tratos en el mismo mensaje se nota y suena a robot.
- 🔴 CERO EMOJIS. Ni uno, aunque la frase sea triste o simpática.
  Solo si la otra persona usó emojis primero, ahí puedes usar uno.
- 🔴 WhatsApp NO entiende markdown. La negrita va con UN asterisco: *así*.
  Si escribes **así**, al cliente le llegan los asteriscos en pantalla y se ve
  a medio hacer. Nada de ##, guiones de lista ni ```. Texto plano y punto.
- Nunca digas que eres un bot ni un asistente virtual. Tampoco lo niegues si
  preguntan directo: en ese caso di que puedes ayudar con horas e información y
  que para lo demás pasas con alguien del equipo.

=== LAS TRES REGLAS QUE NO SE ROMPEN ===

1. SOLO DICES LO QUE ESTÁ ARRIBA. CUALQUIER DATO, NO SOLO LOS PRECIOS.

   Precios, horarios, servicios, condiciones, convenios, descuentos, promociones,
   estacionamiento, si aceptan tal cosa: si no está escrito arriba, NO LO SABES.

   🔴 Y "no saberlo" NO es decir que sí y después confirmar.
   Nunca empieces con "Sí, tenemos..." o "Sí, trabajamos con..." para algo que
   no está arriba. Eso ya es una promesa, y el cliente se queda con el sí aunque
   después la corrijan.

   MAL:  "Sí, trabajamos con convenios de empresa. Déjeme confirmar los detalles."
   BIEN: "Eso lo maneja directamente el equipo, déjeme consultarlo y le confirmo."

   Fíjate en la diferencia: la primera afirma que existen, la segunda no afirma
   nada. Si resulta que el negocio NO tiene convenios, la primera ya mintió.

2. NO DIAGNOSTICAS NUNCA.
   Si describen síntomas, no dices qué puede ser ni si es grave ni qué hacer.
   Ofreces una hora y, si suena urgente, pasas de inmediato con una persona.

3. TE RINDES RÁPIDO.
   Ante cualquier cosa de la lista "PASAR A UNA PERSONA", no improvisas.
   Dices que lo ve alguien del equipo al tiro y respondes:
   [ESCALAR: motivo en pocas palabras]
   Esa marca la lee el sistema, el cliente no la ve.

=== AGENDAR ===

🔴 NUNCA REPITAS UNA FECHA U HORA QUE NO ESTÉ ESCRITA EN ESTA CONVERSACIÓN.

Si la persona se despide con un "ya, gracias, nos vemos" y tú NO tienes arriba
el día y la hora que quedaron, **no los inventes**. Preguntas:

  "Perfecto. ¿Me confirma el día y la hora que quedamos?"

Suena peor decir eso que soltar una fecha con seguridad, y aun así es lo
correcto. Una hora inventada hace que el cliente llegue el día equivocado, y
eso el negocio lo paga con un cliente enojado y una hora perdida.

**Esto ya pasó de verdad**: se agendó peluquería para el lunes a las 17:00 y al
despedirse el agente dijo "nos vemos el martes a las 10:00". Nadie se lo había
dicho: sonaba razonable y con eso bastó.

Vale igual para el nombre, el servicio y el precio. Si no está
escrito arriba, no lo sabes.

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


def a_formato_whatsapp(texto):
    """Markdown → lo que WhatsApp sí entiende.

    Al modelo se le pide en el prompt que no use markdown y aun así lo usa: es
    la forma en que aprendió a escribir. Pedirlo no basta, así que se corrige
    acá. WhatsApp marca negrita con UN asterisco (*así*); con dos, al cliente le
    llegan los asteriscos en pantalla y el mensaje se ve a medio hacer.
    """
    if not texto:
        return texto
    texto = re.sub(r"\*\*\*(.+?)\*\*\*", r"*\1*", texto, flags=re.S)  # ***x*** → *x*
    texto = re.sub(r"\*\*(.+?)\*\*", r"*\1*", texto, flags=re.S)      # **x**   → *x*
    texto = re.sub(r"(?m)^#{1,6}\s*", "", texto)                       # títulos
    texto = re.sub(r"(?m)^[ \t]*[-*+][ \t]+", "• ", texto)             # viñetas
    texto = texto.replace("```", "")
    return texto.strip()


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
        salida = a_formato_whatsapp(texto.strip())

        # Última barrera antes de que el cliente lea nada: si el agente nombró un
        # día o una hora que no existen, no se envía. Vale más pedir un momento
        # que mandar a alguien a la clínica un día equivocado.
        ok, problemas = verificar_agenda(salida)
        if not ok:
            print(f"  ⚠️  respuesta bloqueada: {'; '.join(problemas)}")
            marcas = [l for l in salida.split("\n")
                      if l.strip().startswith(("[ESCALAR:", "[AGENDAR:"))]
            salida = respuesta_segura()
            if marcas:
                salida += "\n" + "\n".join(marcas)

        return salida, costo
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


DIAS = ("lunes", "martes", "miércoles", "miercoles", "jueves",
        "viernes", "sábado", "sabado", "domingo")


def _normaliza(s):
    """miércoles → miercoles. El modelo escribe con y sin tilde indistintamente."""
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        s = s.replace(a, b)
    return s.lower().strip()


def verificar_agenda(texto, agenda=None):
    """Comprueba que los días y horas que el agente menciona EXISTAN de verdad.

    Por qué está en código y no en el prompt: el prompt ya trae la instrucción
    "antes de decir que sí a una hora, búscala en la lista", en mayúsculas y con
    la consecuencia explicada. Aun así, probándolo en vivo el 6-ago:

      · Al cambiar de hora a mitad de conversación confirmó las 11:00 de un día
        en que las 11:00 no estaban libres.
      · Al rechazar una hora ocupada ofreció como alternativa "el lunes 10",
        un día que no existe en ninguna agenda.

    Un modelo que tiene el dato correcto delante igual improvisa cuando el
    historial se alarga. Pedírselo no basta; comprobarlo sí.

    Devuelve (ok, problemas). No reescribe el texto: quien llama decide.
    """
    agenda = agenda if agenda is not None else cargar(AGENDA, {})
    dias_reales = {_normaliza(k): v for k, v in agenda.items() if not k.startswith("_")}
    if not dias_reales or not texto:
        return True, []

    problemas = []
    # El (?![\d:]) es lo que separa "lunes 28" (día) de "lunes 10:00" (hora).
    # Tiene que excluir dígitos además de los dos puntos: con solo (?!\s*:) el
    # motor retrocede, prueba "1" en vez de "10", y el falso positivo vuelve.
    # Sin él, "el lunes 10:00 está disponible" se lee como el día 10 y se
    # bloquea una respuesta perfectamente correcta.
    patron_dia = r"(" + "|".join(DIAS) + r")\s+(\d{1,2})(?![\d:])"
    patron_hora = r"\b([01]?\d|2[0-3]):([0-5]\d)\b"

    # Se evalúa oración por oración, y dentro de la oración CADA HORA SE ASOCIA
    # AL DÍA QUE LA PRECEDE. Emparejar todos los días con todas las horas de la
    # frase parece más seguro y no lo es: en "el lunes 28 a las 12:00 y el
    # martes 29 a las 15:00" inventaría dos combinaciones que nadie dijo, y
    # bloquearía una respuesta correcta. Bloquear lo bueno es tan malo como
    # dejar pasar lo malo: si el agente se traba con respuestas válidas, deja
    # de servir.
    for frase in re.split(r"(?<=[.!?\n])\s+", texto):
        f = _normaliza(frase)
        dias = [(m.start(), f"{m.group(1)} {int(m.group(2))}")
                for m in re.finditer(patron_dia, f)]
        if not dias:
            continue

        for _, clave in dias:
            if clave not in dias_reales:
                problemas.append(f"el día «{clave}» no existe en la agenda")

        for m in re.finditer(patron_hora, f):
            previos = [d for d in dias if d[0] < m.start()]
            if not previos:
                continue  # hora suelta antes de nombrar cualquier día: no se juzga
            clave = previos[-1][1]
            if clave not in dias_reales:
                continue  # ya se reportó como día inexistente
            h = f"{int(m.group(1)):02d}:{m.group(2)}"
            if h not in {x.strip() for x in dias_reales[clave]}:
                problemas.append(f"«{clave} a las {h}» no está libre")

    return (not problemas), problemas


def respuesta_segura(agenda=None, maximo=4):
    """Lo que se dice cuando la verificación falla. Solo horas que existen."""
    agenda = agenda if agenda is not None else cargar(AGENDA, {})
    reales = [(k, v) for k, v in agenda.items() if not k.startswith("_") and v]
    if not reales:
        return ("Déjeme revisar la agenda y le confirmo en un momento.")

    lineas = [f"{dia} · {', '.join(horas[:3])}" for dia, horas in reales[:maximo]]
    return ("Déjeme revisar bien la agenda para no darle una hora equivocada.\n\n"
            "Estas son las que tengo libres:\n" + "\n".join(lineas) +
            "\n\n¿Alguna de esas le acomoda?")


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
