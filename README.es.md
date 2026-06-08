# Ditoo Pro × Claude Code — mascota de estado en vivo

🌐 [English](README.md) · [Português](README.pt.md)

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-Ventura+-000000?logo=apple&logoColor=white)
![Bluetooth](https://img.shields.io/badge/Bluetooth-Classic%20RFCOMM-0082FC?logo=bluetooth&logoColor=white)
![Claude Code](https://img.shields.io/badge/Claude_Code-hooks-D4A574?logo=anthropic&logoColor=white)
![Divoom](https://img.shields.io/badge/Divoom-Ditoo_Pro-FF6B35?logoColor=white)

Tu **Divoom Ditoo Pro** se convierte en una mascota en tiempo real mientras trabajas con Claude Code.  
Muestra lo que Claude está haciendo — pensando, escribiendo, esperando — y vuelve a tu reloj normal en el momento en que cierras la sesión, liberando el dispositivo como parlante Bluetooth de tu Mac.

![demo](demo.gif)

---

## Cómo se ve

| Mientras Claude está… | El Ditoo muestra |
|-----------------------|------------------|
| Esperando tu próximo prompt | criatura naranja, parpadeo ocasional |
| Pensando | puntos de pensamiento girando arriba |
| Usando una herramienta / escribiendo una respuesta | mirando hacia abajo + cursor parpadeando |
| Listo con una respuesta | ojos `^^` felices + tilde verde |
| Sin sesión abierta | tu reloj normal |

---

## Qué necesitas

- **Divoom Ditoo Pro** (la pantalla de píxeles, no otros modelos Divoom)
- **Mac** con macOS Ventura 13 o posterior
- **Claude Code** instalado y funcionando (`claude --version` debe responder)
- **Python 3** — ya viene en todas las Macs, no hay nada extra que instalar

---

## Instalación — 5 pasos

### Paso 1 — Empareja el Ditoo Pro con tu Mac

Abre **Configuración del Sistema → Bluetooth**, busca `DitooPro-Audio` y conéctalo.  
Déjalo conectado durante el resto de la configuración.

---

### Paso 2 — Encuentra la dirección MAC Bluetooth del Ditoo

Ejecuta esto en la Terminal:

```sh
system_profiler SPBluetoothDataType | grep -A8 -i ditoo
```

Busca la línea `Address:`. Se verá algo así: `B1:21:81:8C:C0:B5`.  
Anótala — la usarás exactamente como aparece en el paso siguiente.

---

### Paso 3 — Clona y despliega

```sh
git clone https://github.com/linuxshark/Divoom-Ditto-Pro-Claude-Code.git
cd Divoom-Ditto-Pro-Claude-Code
sh tools/deploy.sh
```

Esto copia todo a `~/.ditoo` y crea un entorno virtual de Python ahí.  
Se instala fuera de `~/Documents` para evitar las restricciones de privacidad de macOS.

---

### Paso 4 — Configura la dirección MAC de tu dispositivo

Agrega esta línea a tu `~/.zshrc` (o `~/.bash_profile` si usas bash):

```sh
export DITOO_MAC=B1:21:81:8C:C0:B5   # ← pega tu dirección del Paso 2, cualquier formato funciona
```

Luego recarga el shell:

```sh
source ~/.zshrc
```

---

### Paso 5 — Agrega los hooks de Claude Code

Abre `~/.claude/settings.json` en cualquier editor de texto y agrega el bloque `"hooks"` que ves abajo.  
Si ya tienes hooks para otras herramientas, **fusiona** las claves — no reemplaces todo el objeto `"hooks"`.

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py start", "timeout": 3 }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py end", "timeout": 3 }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py thinking", "timeout": 3 }] }
    ],
    "PreToolUse": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py thinking", "timeout": 3 }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py writing", "timeout": 3 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py done", "timeout": 3 }] }
    ]
  }
}
```

**Listo.** Abre una sesión de Claude Code — aparece la mascota. Ciérrala — vuelve tu reloj.

---

## Una nota sobre el audio Bluetooth

macOS no puede usar RFCOMM (el canal de pantalla) y A2DP (audio Bluetooth) en el mismo dispositivo al mismo tiempo.  
Mientras hay una sesión de Claude Code activa, el Ditoo no está disponible como parlante de la Mac.  
En el momento en que cierras la sesión, el daemon libera el canal y tu reloj (y el audio) vuelven automáticamente.

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| Nada pasa al iniciar sesión | Hooks no agregados | Revisa el Paso 5 — verifica `~/.claude/settings.json` |
| El Ditoo muestra el reloj equivocado | `DITOO_MAC` no está configurado o es incorrecto | Revisa el Paso 4, ejecuta `echo $DITOO_MAC` en una terminal nueva |
| El daemon inicia pero la pantalla queda en blanco | Ditoo no conectado por BT | Abre Bluetooth y reconéctalo |
| El reloj no vuelve después de la sesión | Daemon aún corriendo de sesión anterior | `pkill -TERM -f "ditoo/daemon.py"` |
| Error de permiso Bluetooth | Primera ejecución necesita contexto de terminal | Siempre inicia Claude Code desde Terminal, no desde Spotlight o Finder |

---

<details>
<summary>⚙️ Detalles técnicos — arquitectura, protocolo, notas de hardware, personalización, tests</summary>

## Cómo funciona

```
Hooks de Claude Code ──(JSON sobre /tmp/ditoo.sock)──> daemon ──(RFCOMM/SPP)──> Ditoo Pro
```

- `hooks/notify.py` es invocado por cada hook de Claude Code con un nombre de estado. Envía
  una línea JSON al socket Unix del daemon y, si el daemon no está corriendo, **lo inicia
  automáticamente** (ver nota de Bluetooth más abajo).
- `daemon.py` controla la conexión Bluetooth. El **hilo principal** corre el CFRunLoop de
  IOBluetooth y mantiene el canal RFCOMM; un hilo en segundo plano atiende el socket Unix.
  Cuenta las sesiones activas, muestra la mascota mientras haya alguna abierta y vuelve al
  reloj cuando no queda ninguna.
- `divoom_proto.py` — codificador de protocolo puro (imágenes de paleta, animaciones, el
  comando `SET_VIEW` del reloj). `pixels_loader.py` carga el arte `pixels/*.json` en paquetes
  listos para enviar. `transport.py` — el transporte RFCOMM de IOBluetooth para macOS
  (+ un `MockTransport` para tests).

### Módulos

| Archivo | Rol |
|---------|-----|
| `divoom_proto.py` | Codificador de protocolo de wire puro (sin I/O) |
| `transport.py` | Transporte RFCOMM IOBluetooth para macOS + mock |
| `pixels_loader.py` | `pixels/*.json` → paquetes codificados |
| `daemon.py` | Daemon con sesiones (socket + runloop + retorno al reloj) |
| `hooks/notify.py` | Hook → notificador de socket, arrancador lazy del daemon |
| `tools/gen_art.py` | Genera el arte de la mascota (`pixels/*.json`) |
| `tools/png_to_pixels.py` | Convierte un PNG/GIF al formato JSON de arte |
| `tools/deploy.sh` | Despliega el runtime autónomo en `~/.ditoo` |

### Re-desplegar después de cambios

Después de editar código o regenerar arte, corre `sh tools/deploy.sh` nuevamente para
actualizar `~/.ditoo`, luego reinicia el daemon:

```sh
pkill -TERM -f "ditoo/daemon.py"
```

Se relanza automáticamente en el próximo hook de Claude Code.

### Personalizar el arte de la mascota

Edita `tools/gen_art.py` (la mascota es una grilla ASCII en `BODY_ROWS`;
`#` = cuerpo, `o` = ojo, espacio = apagado), corre `python tools/gen_art.py`, luego redesplega.

O convierte cualquier imagen: `python tools/png_to_pixels.py art.gif thinking 6 > pixels/thinking.json`

### Cambiar el reloj al que vuelve

El daemon vuelve al **estilo de reloj id 9 en naranja** por defecto. Configura variables de
entorno para cambiarlo:

```sh
export DITOO_CLOCK_ID=9
export DITOO_CLOCK_COLOR=255,120,0  # RGB
```

## ¿Por qué no launchd?

Un **LaunchAgent de macOS no tiene permiso de Bluetooth** (TCC), y el panel de privacidad
de Bluetooth no permite otorgárselo a un binario simple — por eso un daemon ejecutado por
launchd falla silenciosamente al abrir RFCOMM. Los procesos iniciados desde un **contexto
de terminal** sí tienen acceso a Bluetooth, y los hooks de Claude Code corren en ese
contexto. El daemon es iniciado de forma lazy por `hooks/notify.py` y hereda el permiso.
Un `flock` singleton (`/tmp/ditoo.daemon.lock`) garantiza que solo corra un daemon sin
importar cuántas sesiones o hooks se disparen.

## Notas de hardware

El registro completo de ingeniería inversa está en [`spike/NOTES.md`](spike/NOTES.md).
Puntos destacados:

- El transporte es **Bluetooth Classic RFCOMM/SPP** (no BLE), canal 2, solo apertura
  asíncrona. La apertura síncrona devuelve `kIOReturnError`.
- IOBluetooth entrega callbacks de RFCOMM **solo en el CFRunLoop del hilo principal**, y una
  apertura debe iniciarse fuera de un loop en ejecución — de ahí el ciclo start/run_forever.
- `dev.closeConnection()` corta el enlace de audio de macOS para que RFCOMM pueda abrirse.
- El dispositivo **no** revierte automáticamente cuando se cierra el canal; volver al reloj
  requiere un comando explícito `SET_VIEW` (0x45). El reloj del usuario = estilo id 9, naranja.
- Nunca hagas SIGKILL al daemon en medio de RFCOMM (traba el servidor SPP del dispositivo;
  recuperar: apagar y encender el Ditoo). El daemon siempre cierra el canal limpiamente al
  apagarse.

## Tests

```sh
.venv/bin/python -m pytest -q     # 78 tests, sin hardware necesario
```

`MockTransport` hace que el protocolo, el loader y la lógica del daemon sean completamente
testeables sin un dispositivo físico.

</details>
