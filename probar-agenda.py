#!/usr/bin/env python3
"""Pruebas de la verificación de agenda.

Existe porque el 6-ago el agente confirmó una hora ocupada y ofreció un día que
no existía, teniendo la lista correcta delante y con la instrucción escrita en
mayúsculas en el prompt. El README decía que ese bug estaba arreglado y no lo
estaba: se había probado cada caso en una conversación limpia, nunca cambiando
de hora a mitad de conversación, que es justo donde falla.

Una regla sin prueba es una regla que no sabes si funciona.

    python3 probar-agenda.py
"""
import sys
import agente

AGENDA = {
    "_nota": "agenda de prueba, no se toca la real",
    "lunes 28": ["10:00", "10:30", "12:00", "16:30", "17:00"],
    "martes 29": ["09:30", "11:00", "15:00", "18:00"],
    "miércoles 30": ["10:00", "11:30", "16:00", "18:30"],
}

# (descripción, texto, debe_pasar)
CASOS = [
    # --- lo que DEBE bloquear ---
    ("hora ocupada confirmada (el fallo del 6-ago)",
     "Claro, el lunes 28 a las 11:00 está disponible. ¿A nombre de quién?", False),

    ("día que no existe (la alternativa inventada)",
     "El lunes 28 no tengo. ¿Le sirve el lunes 10 a las 11:00?", False),

    ("hora inventada al despedirse",
     "De nada, queda agendado. Nos vemos el martes 29 a las 10:00.", False),

    ("día correcto pero hora fuera de lista",
     "Perfecto, la dejo para el miércoles 30 a las 09:00.", False),

    ("mezcla: una buena y una mala en la misma respuesta",
     "El lunes 28 a las 10:00 está libre. También tengo el lunes 28 a las 11:00.", False),

    # --- lo que DEBE dejar pasar ---
    ("hora libre confirmada correctamente",
     "Perfecto. El lunes 28 a las 10:00 está disponible. ¿A nombre de quién?", True),

    ("varias horas, todas reales",
     "Tengo el lunes 28 a las 12:00 y el martes 29 a las 15:00. ¿Cuál le acomoda?", True),

    ("sin días ni horas",
     "La consulta general sale $25.000 y dura 30 minutos. ¿Necesita agendar?", True),

    ("menciona un día sin hora",
     "El lunes 28 tengo varios horarios. ¿En la mañana o en la tarde?", True),

    ("hora sin día, no se puede verificar y no se bloquea",
     "Tengo a las 10:00 disponible, ¿le sirve?", True),

    ("día escrito sin tilde",
     "El miercoles 30 a las 11:30 está libre.", True),

    ("precio con dos puntos que NO es una hora",
     "Son 3 sesiones. El lunes 28 a las 12:00 le queda bien.", True),

    # Este falso positivo apareció en la primera prueba real contra el modelo:
    # "el lunes 10:00" se leía como el día 10 y bloqueaba una respuesta correcta.
    ("«lunes 10:00» es una hora, no el día 10",
     "Perfecto. El lunes 10:00 está disponible. ¿A nombre de quién?", True),

    ("«martes 09:30» sin la palabra 'las' tampoco es un día",
     "Le queda el martes 09:30 entonces.", True),
]


def main():
    fallos = 0
    for desc, texto, debe_pasar in CASOS:
        ok, problemas = agente.verificar_agenda(texto, AGENDA)
        bien = (ok == debe_pasar)
        marca = "✅" if bien else "❌"
        esperado = "pasar" if debe_pasar else "bloquear"
        print(f"  {marca} [{esperado:>8}] {desc}")
        if not bien:
            fallos += 1
            print(f"       texto: {texto}")
            print(f"       dio: {'pasó' if ok else 'bloqueó'} · {problemas}")

    # La respuesta de rescate no puede inventar tampoco: solo horas de la agenda.
    segura = agente.respuesta_segura(AGENDA)
    ok, problemas = agente.verificar_agenda(segura, AGENDA)
    marca = "✅" if ok else "❌"
    print(f"  {marca} [ pasar] la respuesta de rescate solo usa horas reales")
    if not ok:
        fallos += 1
        print(f"       {problemas}")

    total = len(CASOS) + 1
    print(f"\n  {total - fallos}/{total}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
