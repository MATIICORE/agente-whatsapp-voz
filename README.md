# Agente de atención por WhatsApp, con voz

Un agente que contesta el WhatsApp de un negocio: entiende notas de voz, responde
hablando, y consulta la agenda real antes de comprometer una hora.

Está construido para negocios chicos —una veterinaria, una peluquería, un centro
médico— donde el dueño pierde clientes simplemente porque estaba atendiendo cuando
llegó el mensaje.

Los datos de este repositorio son de una veterinaria ficticia. Los precios sí son
reales de mercado chileno 2026.

---

## Qué hace

| | |
|---|---|
| 🎙️ | **Escucha notas de voz.** Transcripción con Whisper corriendo local: costo cero. |
| 🔊 | **Responde con nota de voz** (ElevenLabs) o con texto. |
| 📅 | **Lee el Google Calendar en vivo** y solo ofrece horas que estén libres de verdad. |
| 🚩 | **Escala a una persona** cuando la consulta se sale de su alcance. |
| 💰 | **Mide su propio costo** por conversación. |

## Cómo está armado

```
negocio.json    precios, horarios, servicios, y qué NO hace el negocio
agente.py       el cerebro — API de Anthropic, modelo Haiku
voz.py          escuchar (Whisper local) y hablar (ElevenLabs)
agenda.py       lee el Google Calendar por iCal
flujo.py        el ciclo completo: entra audio → sale audio
demo/           una pantalla que imita WhatsApp, para mostrarlo
```

Sin dependencias externas para hablar con la API: solo `urllib` de la librería
estándar. Corre en cualquier Mac sin instalar nada.

## Correrlo

```bash
cp .env.ejemplo .env      # y poner las llaves
python3 agente.py         # conversación por terminal
python3 demo/servidor.py  # demo web en http://localhost:7500
```

---

## Las decisiones que importan

### 1. El agente solo lee la agenda. Nunca escribe en ella.

Cuando alguien quiere una hora, el agente deja una marca interna `[AGENDAR: ...]`
para que una persona confirme. No toca el calendario del negocio.

Esto salió de hablar con una clínica real: la persona a cargo maneja tres agendas y
prefiere manejarlas ella. Un agente que le escriba solo en la agenda es exactamente
lo que no quiere.

### 2. Las marcas internas no las ve el cliente

`[ESCALAR: motivo]` y `[AGENDAR: ...]` se separan de la respuesta antes de enviarla.
El sistema las lee, la persona del otro lado no.

### 3. Nunca diagnostica

Ante síntomas, el agente no dice qué puede ser ni qué hacer: ofrece una hora y, si
suena urgente, pasa con una persona. Esto no es una limitación técnica, es lo que
separa un agente que se puede vender de uno que le crea un problema legal al negocio.

---

## 🔴 Los dos errores que aparecieron probándolo

Los dos aparecieron rompiendo el agente a propósito antes de mostrárselo a nadie.
Los dejo escritos porque son la parte útil del proyecto.

### Inventó un dato que sonaba razonable

Le preguntaron por el servicio de peluquería y respondió que *"el baño ya viene
incluido"*. Eso no estaba escrito en ninguna parte: lo dedujo porque suena lógico.
Probablemente hasta es cierto, pero el agente no lo sabía.

**La lección:** mientras más detallado el archivo del negocio, menos espacio hay para
inventar. En vez de `"Peluquería grande: $28.000"`, va
`"Peluquería grande: $28.000 — incluye baño, corte y secado. No incluye uñas."`

Esa es la parte aburrida del trabajo y es la que decide si el agente sirve.

### Confirmó una hora que estaba ocupada

Le pidieron el lunes a las 10:00, que estaba tomado, **y dijo que sí**. El agente
tenía la lista de horas libres correcta en su contexto. No la revisó antes de
responder.

Se arregló con una instrucción explícita de buscar la hora en la lista antes de
confirmar, y explicando la consecuencia concreta: el cliente llega y hay otro animal
en la mesa. Verificado después en los dos sentidos: hora ocupada la rechaza y ofrece
alternativas reales, hora libre la confirma.

> **Que el modelo tenga el dato correcto no basta. Hay que decirle explícitamente que
> lo verifique.**

---

## ⚠️ Zona horaria

Google entrega las horas del calendario en UTC. Sin convertir, un evento de las 10:00
en Chile se lee como las 14:00 y el agente termina ofreciendo horas ocupadas. Ya está
corregido en `agenda.py`, pero es el primer lugar donde mirar si las horas salen
raras.

## Costo real, medido

| | |
|---|---|
| Un mensaje de texto | ~$2 CLP |
| Escuchar una nota de voz | $0 — Whisper corre local |
| Responder con voz | ~$6,5 CLP (ElevenLabs) |
| **Conversación completa con voz** | **~$8,4 CLP en 6,4 segundos** |

Medido instrumentando el flujo completo, no estimado desde la tabla de precios.

## Licencia

MIT
