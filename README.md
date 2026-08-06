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
whatsapp.py     el puente a la Meta Cloud API — esto es lo que corre en producción
verificar-meta.py  valida las llaves contra la API de Meta antes de configurar nada
arrancar.sh     levanta agente y túnel, e imprime la dirección lista para pegar
estado.sh       responde en 5 segundos si está vivo, sin entrar a Meta
demo/           una pantalla que imita WhatsApp, para mostrarlo sin conectar nada
```

Sin dependencias externas para hablar con las APIs: solo `urllib` de la librería
estándar. Corre en cualquier Mac sin instalar nada.

## Correrlo

```bash
cp .env.ejemplo .env      # y poner las llaves
python3 agente.py         # conversación por terminal
python3 demo/servidor.py  # demo web en http://localhost:7500
```

Para conectarlo a WhatsApp de verdad: [`CONECTAR-WHATSAPP.md`](CONECTAR-WHATSAPP.md).

---

## En producción, sobre la Meta Cloud API

`whatsapp.py` es el puente a WhatsApp. Se eligió la **Meta Cloud API** y no las
alternativas por dos motivos concretos: Twilio cobra por mensaje, y las librerías que
manejan WhatsApp Web (Baileys, whatsapp-web.js) **banean el número**. Para el negocio
de un cliente, eso no es una opción.

Un dato que cambia el modelo de negocio: **Meta no cobra por responder.** Cuando un
cliente escribe se abre una ventana de 24 horas y todo lo que el agente conteste ahí
vale cero. Solo se cobran las plantillas que inicia el negocio, y el agente no hace
eso.

### Lo que hubo que resolver para que aguantara

**Verificar la firma de cada POST.** Meta firma cada webhook con
`X-Hub-Signature-256`. Sin comprobarla, la dirección del webhook es una puerta
abierta: cualquiera que la sepa inyecta mensajes falsos y gasta la cuenta de API del
negocio. Se compara con `hmac.compare_digest`, no con `==`.

**Responder 200 al instante y pensar en otro hilo.** Si el webhook tarda, Meta
reenvía el mismo mensaje una y otra vez y el agente entra en bucle contestando lo
mismo.

**Un candado por número.** Dos mensajes seguidos del mismo cliente se procesaban en
paralelo y el segundo pisaba el historial del primero. Con notas de voz era casi
seguro que pasara, porque cada una tarda entre 6 y 8 segundos entre transcribir,
pensar y hablar.

**La memoria va a disco, no a RAM.** Estaba solo en memoria y falló de verdad: al
reiniciar el agente para actualizar el código, un cliente en pleno diálogo tuvo que
repetir lo que ya había dicho. Ahora vive en `conversaciones.json` y se limpia sola a
las 24 horas, que es lo que dura la ventana de WhatsApp. Ese archivo está en
`.gitignore`: lleva nombres, teléfonos y consultas reales, y este repo es público.

**WhatsApp no entiende markdown.** El modelo escribía `**Plan mensual**` y al cliente
le llegaban los asteriscos en pantalla. Pedírselo en el prompt no bastó, es como
aprendió a escribir. Se corrige en el código, en `a_formato_whatsapp()`, antes de
enviar.

> Cuando una salida tiene que cumplir un formato exacto, se arregla en el código, no
> pidiéndoselo al modelo.

**Responde en el formato en que le hablan.** Si el cliente escribe, contesta escrito.
Si manda un audio, contesta con audio. La nota de voz se sube a Meta como **ogg/opus**:
en mp3 llega como archivo adjunto que hay que descargar, y pierde toda la gracia.

### El paso que no está en ningún tutorial

Suscribirse al campo `messages` en la app **no alcanza**. Hay que suscribir la cuenta
de WhatsApp (WABA) a la app con `POST /{WABA_ID}/subscribed_apps`. Sin eso Meta
verifica el webhook, la pantalla dice "Suscrito", y no llega ni un mensaje: los
eventos se van a la app de pruebas que Meta trae enganchada de fábrica.

Se diagnostica con `GET /{WABA_ID}/subscribed_apps`. Si tu app no aparece ahí, es eso.

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

### Se despidió con una fecha que nadie le había dicho

Apareció ya conectado a WhatsApp de verdad. Se agendó peluquería para el **lunes
a las 17:00**, y cuando el cliente cerró con un *"ok, gracias, nos vemos ahí"*,
el agente respondió: *"De nada, queda agendado. Nos vemos el **martes a las
10:00**"*.

Nadie había mencionado nunca ese día ni esa hora.

Lo que pasó es que ese mensaje le llegó **sin el historial de la conversación**.
Y ahí está lo interesante: teniendo cero información, no dijo que no sabía.
Rellenó el hueco con una fecha que sonaba razonable y la afirmó con total
seguridad.

**La lección:** un modelo sin contexto no se queda callado, improvisa. Y una
fecha inventada es peor que un precio inventado, porque el cliente llega el día
equivocado y el negocio pierde la hora y al cliente.

Se arregló con una instrucción explícita para las despedidas: si el día y la
hora no están escritos en la conversación, preguntar. Verificado después:
ahora responde *"Perfecto. ¿Me confirma el día y la hora que quedamos?"*.

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
