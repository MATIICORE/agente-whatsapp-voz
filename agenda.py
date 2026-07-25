#!/usr/bin/env python3
"""
La agenda del negocio.

Lee un Google Calendar por su URL secreta de iCal. No necesita OAuth ni permisos:
el dueño publica el calendario, pega la URL en negocio.json, y listo.

El agente SOLO LEE. Nunca escribe en la agenda del negocio: cuando alguien quiere
una hora, se le avisa al dueño para que confirme. Así nadie pierde el control de
su propio día, y si el agente entendió mal, alguien lo caza antes.

Uso:
    python3 agenda.py            muestra las horas libres de la semana
    python3 agenda.py ocupadas   muestra lo que ya está tomado
"""
import datetime as dt
import json, os, re, sys, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
NEGOCIO = os.path.join(BASE, "negocio.json")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def cargar_negocio():
    with open(NEGOCIO, encoding="utf-8") as f:
        return json.load(f)


def url_calendario():
    """
    La URL secreta del calendario.

    Vive en el .env y NO en negocio.json: quien la tiene puede leer todo el
    calendario, así que es una credencial, no un dato del negocio.
    """
    v = os.environ.get("CALENDARIO_ICAL", "").strip()
    if v:
        return v
    try:
        with open(os.path.join(BASE, ".env"), encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith("CALENDARIO_ICAL"):
                    return linea.split("=", 1)[1].strip().strip("'\"")
    except FileNotFoundError:
        pass
    # compatibilidad: si alguien la dejó en negocio.json, igual funciona
    try:
        return cargar_negocio().get("calendario_ical")
    except Exception:
        return None


# ── Leer el calendario ───────────────────────────────────────────────────────

def _desdoblar(texto):
    """iCal parte las líneas largas y las continúa con un espacio al inicio."""
    return re.sub(r"\r?\n[ \t]", "", texto)


def _fecha(valor):
    """
    Convierte una fecha de iCal a hora LOCAL.

    ⚠️ Google entrega las horas en UTC (terminan en Z). Sin convertir, un evento
    de las 10:00 en Chile se lee como las 14:00 y el agente ofrece horas que en
    realidad están ocupadas. Chile es UTC-4 (UTC-3 en horario de verano), así que
    la conversión la hace el sistema, no un número fijo.
    """
    v = valor.strip()
    en_utc = v.endswith("Z")
    v = v.rstrip("Z")
    for formato in ("%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            f = dt.datetime.strptime(v, formato)
            if en_utc:
                f = f.replace(tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
            return f
        except ValueError:
            continue
    return None


def eventos(url, desde=None, hasta=None):
    """Devuelve los eventos del calendario entre dos fechas."""
    desde = desde or dt.datetime.now()
    hasta = hasta or (desde + dt.timedelta(days=7))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            crudo = _desdoblar(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return None, f"no pude leer el calendario: {e}"

    out = []
    for bloque in crudo.split("BEGIN:VEVENT")[1:]:
        ini = fin = None
        for linea in bloque.split("\n"):
            if linea.startswith("DTSTART"):
                ini = _fecha(linea.split(":", 1)[-1])
            elif linea.startswith("DTEND"):
                fin = _fecha(linea.split(":", 1)[-1])
        if ini and desde <= ini <= hasta:
            out.append((ini, fin or ini + dt.timedelta(hours=1)))
    return sorted(out), None


# ── Calcular qué queda libre ─────────────────────────────────────────────────

def _horario_del_dia(negocio, fecha):
    """Devuelve (hora_apertura, hora_cierre) o None si está cerrado."""
    h = negocio["horarios"]
    dia = fecha.weekday()
    if dia <= 4:
        rango = h.get("lunes_a_viernes", "")
    elif dia == 5:
        rango = h.get("sabado", "")
    else:
        return None
    m = re.findall(r"(\d{1,2}):(\d{2})", rango)
    if len(m) < 2:
        return None
    return (int(m[0][0]), int(m[1][0]))


def libres(dias=7, paso_min=30):
    """Las horas disponibles de los próximos días, según el horario y lo tomado."""
    negocio = cargar_negocio()
    url = url_calendario()
    if not url:
        return None, ("falta el calendario. En negocio.json agrega:\n"
                      '  "calendario_ical": "https://calendar.google.com/calendar/ical/.../basic.ics"')

    ahora = dt.datetime.now()
    ocupado, err = eventos(url, ahora, ahora + dt.timedelta(days=dias))
    if err:
        return None, err

    resultado = {}
    for d in range(dias):
        fecha = (ahora + dt.timedelta(days=d)).replace(minute=0, second=0, microsecond=0)
        horario = _horario_del_dia(negocio, fecha)
        if not horario:
            continue
        apertura, cierre = horario

        huecos = []
        t = fecha.replace(hour=apertura)
        while t.hour < cierre:
            # solo horas futuras, y que no choquen con algo ya agendado
            if t > ahora and not any(a <= t < b for a, b in ocupado):
                huecos.append(t.strftime("%H:%M"))
            t += dt.timedelta(minutes=paso_min)

        if huecos:
            etiqueta = f"{DIAS[fecha.weekday()]} {fecha.day}"
            resultado[etiqueta] = huecos
    return resultado, None


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ocupadas":
        ev, err = eventos(url_calendario() or "")
        if err:
            print(f"❌ {err}")
        else:
            for a, b in ev:
                print(f"  {DIAS[a.weekday()]} {a.day} · {a:%H:%M} a {b:%H:%M}")
    else:
        h, err = libres()
        if err:
            print(f"❌ {err}")
        else:
            for dia, horas in h.items():
                print(f"  {dia}: {', '.join(horas)}")
