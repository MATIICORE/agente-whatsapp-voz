# Conectar el agente a WhatsApp de verdad

El agente ya funcionaba, pero solo en la terminal y en una demo que imitaba
WhatsApp. Esto lo enchufa a la Cloud API oficial de Meta.

**El código ya está hecho** (`whatsapp.py`). Lo que falta son cuentas y llaves, y
esa parte la tienes que hacer tú: yo no puedo crear cuentas ni aceptar términos.

## Lo primero, porque cambia el cálculo

**Meta no te cobra por responder.** Textual de su documentación: *"All non-template
messages are free"*. Cuando un cliente escribe, se abre una ventana de 24 horas y
todo lo que el agente conteste dentro de esa ventana **vale cero.**

Lo que se cobra son las plantillas que inicia el negocio (marketing, recordatorios
fuera de ventana). Tu agente no hace eso: contesta a quien escribe.

Entonces el costo por conversación sigue siendo el que ya tenías medido:

| | |
|---|---|
| WhatsApp | **$0** |
| Pensar la respuesta (Haiku) | ~$2 CLP el mensaje |
| Escuchar una nota de voz | **$0** — Whisper corre en tu Mac |
| Responder con voz (ElevenLabs) | ~$6,5 CLP |
| **Conversación completa** | **~$8,4 CLP** |

A $50.000 el plan mensual, eso son unas 5.900 conversaciones antes de perder plata.
Ningún negocio chico se acerca a esa cifra.

---

## Los 6 pasos

### 1 · Cuenta de desarrollador
[developers.facebook.com](https://developers.facebook.com) → entrar con tu Facebook
y registrarte como desarrollador. Gratis.

### 2 · Crear la app
**Mis apps → Crear app → caso de uso "WhatsApp"**. Te va a pedir una cuenta de Meta
Business; si no tienes, la crea ahí mismo.

### 3 · Sacar las tres llaves
En **WhatsApp → Configuración de la API** vas a ver:

| Dónde dice | Qué es | Va en el .env |
|---|---|---|
| *Token de acceso temporal* | dura 24 horas, sirve para probar | `WA_TOKEN` |
| *Identificador del número de teléfono* | **no es el número**, es un id largo | `WA_PHONE_ID` |
| Configuración → Básica → *Clave secreta de la app* | hay que darle "Mostrar" | `WA_APP_SECRET` |

Meta te regala un **número de prueba** con el que puedes escribirle hasta a 5
teléfonos que registres tú. Con eso alcanza y sobra para probar todo esto sin
pagar ni verificar nada.

### 4 · Llenar el .env

```
WA_TOKEN=EAAxxxxxxxxx
WA_PHONE_ID=123456789012345
WA_VERIFY_TOKEN=matiicore-2026
WA_APP_SECRET=abc123def456
```

`WA_VERIFY_TOKEN` es una palabra que **inventas tú**. No se saca de ninguna parte:
solo tiene que ser la misma acá y en el paso 5.

Para revisar que quedó bien:

```bash
cd ~/Claude/4-herramientas/agente-whatsapp && python3 whatsapp.py --probar
```

### 5 · Abrir la puerta a internet

Meta necesita una dirección pública para mandarte los mensajes. Tu Mac no la tiene,
así que se abre un túnel. `cloudflared` ya quedó instalado.

**Terminal 1** — el agente:
```bash
cd ~/Claude/4-herramientas/agente-whatsapp && python3 whatsapp.py
```

**Terminal 2** — el túnel:
```bash
cloudflared tunnel --url http://localhost:7501
```

Te va a imprimir una dirección tipo `https://algo-random.trycloudflare.com`.
**Esa es la que Meta necesita.** Cámbiala cada vez que reinicies el túnel.

### 6 · Conectar el webhook

En Meta: **WhatsApp → Configuración → Webhooks → Editar**

- **URL de devolución de llamada**: la dirección del túnel
- **Token de verificación**: la palabra que inventaste en el paso 4

Le das **Verificar y guardar**. En tu terminal debería aparecer
`✅ Meta verificó el webhook`.

Después, en **Campos del webhook**, suscríbete a **`messages`**. Sin eso Meta
verifica la URL pero no te manda nada.

---

## Probarlo

Escríbele desde tu celular al número de prueba de Meta. En la terminal vas a ver el
mensaje entrando, la respuesta del agente y lo que costó.

Prueba estas tres, que son las que importan:

1. **"¿cuánto sale un baño?"** → tiene que dar el precio exacto de `negocio.json`
2. **"¿tienen hora el lunes a las 10?"** → si está ocupada, **tiene que decir que no**
   y ofrecer otras. Este es el error que ya apareció una vez.
3. **una nota de voz** → la transcribe con Whisper local, gratis

---

## 🔴 Lo que hay que resolver antes de cobrarle a alguien

### El token dura 24 horas
El temporal se vence. Para uno permanente: **Configuración del negocio → Usuarios
del sistema → crear uno → Generar token** con los permisos `whatsapp_business_messaging`
y `whatsapp_business_management`. Ese no se vence.

### La dirección del túnel cambia cada vez
`trycloudflare.com` da una distinta en cada arranque, y hay que ir a actualizarla a
Meta a mano. Para un cliente real hace falta un túnel con nombre fijo (gratis con tu
cuenta de Cloudflare) o dejarlo en un servidor.

### 🔴 Tu Mac tiene que estar prendido
Este es el problema de fondo, no un detalle. El agente corre en tu computador porque
Whisper transcribe ahí. **Si cierras el Mac, el WhatsApp del cliente deja de
responder** — justo lo contrario de lo que le vendiste.

Tres salidas, de menor a mayor:

1. **Para el primer cliente**: dejarlo corriendo y avisarle que estás en marcha
   blanca. Honesto y suficiente para empezar.
2. **VPS de USD 5 al mes**: Whisper no cabe cómodo en el más chico, pero se puede
   transcribir con la API de OpenAI (unos $4 CLP por audio) y ahí el agente corre
   solo, sin tu Mac.
3. **Sin voz**: si el agente contesta solo texto, no necesita Whisper y cabe en
   cualquier servidor chico. Pero la voz es justamente lo que lo hace distinto.

👉 **Decide esto antes de cerrar el primer cliente de agente**, no después.

### Un número por cliente
Cada negocio necesita su propio número en la Cloud API. No puedes atender a dos
clientes con el mismo. El número de prueba de Meta es solo para desarrollo: para
producción, el negocio pone un número suyo que **no esté en uso en WhatsApp normal**
(hay que darlo de baja de la app antes de registrarlo acá).

---

## Cómo está hecho el puente

`whatsapp.py`, sin librerías, igual que el resto del proyecto.

- **Verifica la firma de cada POST** con `X-Hub-Signature-256`. Sin eso el webhook es
  una puerta abierta: quien sepa la dirección puede inyectar mensajes falsos y
  gastarte la API de Anthropic.
- **Contesta 200 al instante** y piensa la respuesta en otro hilo. Si te demoras,
  Meta cree que fallaste y reenvía el mismo mensaje una y otra vez.
- **Descarta ids repetidos**, por si el reenvío igual ocurre.
- **Guarda la conversación de cada número en memoria**, las últimas 6 idas y vueltas.
  A propósito no queda en disco: si reinicias, empieza limpio, y no se acumula un
  archivo con conversaciones de clientes esperando a que alguien lo abra.
- **Las marcas `[ESCALAR:]` y `[AGENDAR:]` salen por la terminal, nunca al cliente.**
  Ahí es donde el negocio tiene que mirar.
