# Subtitles Bridge

CLI personal para convertir subtítulos existentes o generados en pistas
seleccionables dentro de un video nuevo.

![Preview](preview.png)

## Objetivo

Dada una carpeta con uno o más videos:

1. inspeccionar cada MP4 o MKV y sus subtítulos asociados;
2. reutilizar todos los subtítulos válidos encontrados;
3. ejecutar Whisper solamente si no existe ningún subtítulo;
4. generar, en ese caso, un único SRT en el idioma hablado;
5. crear un MKV nuevo con todas las pistas seleccionables;
6. verificar que ningún stream del original se haya perdido o recodificado;
7. mover automáticamente el original y los sidecars utilizados a `trash/`.

El programa no elimina definitivamente archivos. `trash/` es una cuarentena
local para que el usuario revise y borre manualmente lo que ya no necesite.

## Garantías del flujo objetivo

- Se aceptan inicialmente videos `.mp4` y `.mkv`, sin recorrer subcarpetas.
- Todos los subtítulos válidos asociados se incorporan, sin limitar idiomas.
- La existencia de cualquier subtítulo válido evita una transcripción nueva.
- No se traduce automáticamente para completar inglés o español.
- Video, audio y demás streams se copian sin compresión ni recodificación.
- Se conservan todos los audios y sus disposiciones originales.
- Ningún subtítulo queda seleccionado por defecto.
- Nada se mueve a `trash/` antes de verificar y publicar el MKV final.
- Cada sidecar agregado se vincula a su pista mediante un SHA-256 interno para
  impedir que una edición posterior se archive como si fuera el archivo usado.
- No se sobrescriben salidas ni archivos archivados.

Remultiplexar a MKV cambia el contenedor, no la calidad de audio o video. MKV
se eligió porque VLC lo reproduce correctamente y ofrece flexibilidad para
múltiples pistas.

## Estructura esperada

Entrada:

```text
videos/
├── lesson-01.mp4
├── lesson-01.en.srt
└── lesson-01.es.srt
```

Después de una ejecución exitosa:

```text
videos/
├── output/
│   └── lesson-01.subtitled.mkv
└── trash/
    └── lesson-01/
        ├── lesson-01.mp4
        ├── lesson-01.en.srt
        └── lesson-01.es.srt
```

## Estado del proyecto

Las fases P0.1-P0.9 y P1.1-P1.6 están completas. La CLI Python ya conecta
discovery, planner, transcripción fallback, remux, verificación, publicación,
cuarentena, resumen y códigos de salida en un único flujo. `menu.sh` llama esa
misma CLI y puede abrirse desde cualquier directorio sin confundir la raíz del
repositorio con la carpeta de videos.

La configuración P1.2 permite ejecutar solo el preflight, elegir el audio por
video, seleccionar modelo y dispositivo de Whisper y reanudar una salida
existente después de volver a verificarla. Una ambigüedad se informa como
`needs-input` sin ejecutar trabajo; no existen opciones de reemplazo o fuerza.

P1.3 agrega un diagnóstico portable de Python, FFmpeg, FFprobe y el checkpoint
local de Whisper. `setup.sh` ya no intenta instalar Homebrew, LLVM ni paquetes
del sistema: valida requisitos, prepara `.venv` y delega el diagnóstico a la
misma CLI.

P1.4 fija la dependencia directa del flujo principal, admite CPython 3.10 a
3.13 y separa la traducción remota heredada para que la instalación normal no
agregue backends de red ni pins transitivos específicos de una plataforma.

P1.5 agrega una puerta local reproducible y GitHub Actions sobre CPython
3.10-3.13, macOS, Linux y Windows. P1.6 incorpora JSON Lines versionado,
progreso por etapa, tiempos monotónicos, ETA basada en muestras reales y
diagnóstico estructurado de fallos y resultados parciales.

P1.7 está implementado localmente y pendiente de la puerta completa: el menú expone preflight, proceso,
reanudación y doctor como acciones separadas, explica los códigos de salida y
mantiene el restablecimiento del entorno como una opción avanzada que no toca
videos ni las carpetas administradas.

## Menú interactivo

Desde cualquier directorio puede abrirse:

```bash
/ruta/al/repositorio/menu.sh
```

El camino normal es:

1. **Preparar / verificar instalación** la primera vez.
2. **Inspeccionar carpeta sin hacer cambios** para revisar el plan.
3. **Procesar carpeta** cuando no existan decisiones pendientes.
4. **Reanudar archivado pendiente** solamente ante un resultado parcial.

La ruta puede escribirse o arrastrarse desde Finder; Enter utiliza el directorio
actual. El menú también ofrece doctor, ayuda y un restablecimiento avanzado de
`.venv` y caches. Esa última opción exige confirmación y nunca elimina videos,
`output/` o `trash/`.

## Ejecución

Desde cualquier directorio:

```bash
python3 /ruta/al/repositorio/subtitles_bridge_cli.py /ruta/a/videos
```

Desde la raíz del repositorio también puede utilizarse:

```bash
python3 -m subtitles_bridge /ruta/a/videos
```

La ayuda completa muestra ejemplos, seguridad y códigos de salida sin cargar
dependencias multimedia:

```bash
python3 /ruta/al/repositorio/subtitles_bridge_cli.py --help
```

La ruta es opcional y usa el directorio actual por defecto. La CLI muestra el
preflight y, si no existe ninguna ambigüedad, ejecuta automáticamente el plan.
Después de verificar el MKV, mueve el original y los SRT incorporados a
`trash/`; no existe borrado definitivo ni sobrescritura.

Opciones operativas:

```bash
# Inspeccionar y planificar sin modificar archivos
python3 /ruta/al/repositorio/subtitles_bridge_cli.py /ruta/a/videos --preflight

# Elegir el índice de stream de audio que se transcribirá para un video
python3 /ruta/al/repositorio/subtitles_bridge_cli.py /ruta/a/videos \
  --audio lesson-02.mkv=3

# Configurar Whisper; solo se carga si realmente falta todo subtítulo válido
python3 /ruta/al/repositorio/subtitles_bridge_cli.py /ruta/a/videos \
  --whisper-model small --whisper-device mps

# Verificar una salida publicada y reanudar únicamente el archivado pendiente
python3 /ruta/al/repositorio/subtitles_bridge_cli.py /ruta/a/videos --resume

# Emitir preflight, progreso y resultado como un objeto JSON por línea
python3 /ruta/al/repositorio/subtitles_bridge_cli.py /ruta/a/videos \
  --output-format jsonl
```

`--audio` puede repetirse para distintos videos. Sin `--resume`, una salida
existente es una colisión; con `--resume`, solo se acepta si supera nuevamente
el contrato completo. `trash/` nunca se fusiona, reemplaza ni vacía.

`--output-format text` es el valor predeterminado. Con `jsonl`, stdout contiene
exclusivamente registros JSON Lines con esquema `1` y secuencia creciente. La
ETA considera solo `transcribe`, `mux` y `verify` realmente planificados; queda
en `null` hasta disponer de duración multimedia y muestras reales comparables.
Un resultado `partial` incluye el MKV publicado, el destino pendiente y
`--resume` como recuperación segura.

## Instalación y diagnóstico

`setup.sh` puede ejecutarse desde cualquier directorio:

```bash
/ruta/al/repositorio/setup.sh
```

Requiere CPython 3.10, 3.11, 3.12 o 3.13, además de FFmpeg y FFprobe ya
disponibles en `PATH`.
El script no instala paquetes del sistema ni descarga modelos automáticamente.
Instala solamente [`requirements.txt`](requirements.txt), que fija
`openai-whisper==20250625` y delega en Whisper la resolución de sus
dependencias transitivas para la plataforma activa.

El mismo diagnóstico puede ejecutarse sin modificar archivos:

```bash
python3 /ruta/al/repositorio/subtitles_bridge_cli.py --doctor
```

La falta de Python compatible, FFmpeg o FFprobe devuelve código `1`. La falta
de Whisper o del modelo local se informa como advertencia y devuelve `0`, porque
los videos con subtítulos existentes no necesitan transcripción. Para preparar
el modelo predeterminado cuando se acepta usar red:

```bash
"/ruta/al/repositorio/.venv/bin/python3" -c "import whisper; whisper.load_model('small')"
```

El prototipo histórico `local_translate_srt.py` no forma parte de ese setup.
Para reproducir deliberadamente su backend Google —que usa red y puede enviar
texto a un tercero— su dependencia aislada se instala por separado:

```bash
"/ruta/al/repositorio/.venv/bin/python3" -m pip install \
  -r "/ruta/al/repositorio/requirements-legacy.txt"
```

## Pruebas

La red de seguridad inicial usa únicamente la biblioteca estándar de Python y
no ejecuta Whisper, FFmpeg, FFprobe ni servicios de red reales.

Desde la raíz del repositorio:

```bash
python3 -m unittest discover -s tests -v
```

Los casos mostrados como `expected failure` son reproducciones ejecutables de
defectos conocidos del prototipo. Permanecen visibles hasta que la fase que
reemplace o corrija ese comportamiento convierta cada caso en una prueba
normal. Un `unexpected success` hace fallar la suite para evitar mantener una
marca obsoleta.

El inventario de esas reproducciones está en [`tests/README.md`](tests/README.md).
La suite completa ejecuta 223 casos y mantiene 11 defectos del prototipo
legado como `expectedFailure`.

## Checks automáticos

Las herramientas de desarrollo no se instalan mediante `setup.sh`. Para
preparar Ruff dentro del entorno del proyecto:

```bash
"/ruta/al/repositorio/.venv/bin/python3" -m pip install \
  -r "/ruta/al/repositorio/requirements-dev.txt"
```

La puerta local requiere además ShellCheck `0.11.0` y shfmt `3.13.1`
disponibles en `PATH`. Después ejecuta, sin reescribir archivos, formato y lint
de Python/Bash, la suite offline y los smokes reales de `--help` y
`--preflight`:

```bash
"/ruta/al/repositorio/.venv/bin/python3" "/ruta/al/repositorio/tools/check.py"
```

GitHub Actions repite la puerta completa en Linux y ejecuta la suite sobre
CPython 3.10-3.13, macOS, Linux y Windows. No instala Whisper, no descarga
modelos y no invoca FFmpeg/FFprobe durante esos checks.

## Requisitos previstos

- CPython 3.10 a 3.13;
- FFmpeg y FFprobe;
- OpenAI Whisper para el caso sin subtítulos;
- macOS como primera plataforma validada.

El núcleo se mantendrá portable a Linux y Windows. Los scripts shell podrán
facilitar la instalación o el uso interactivo, pero la lógica principal y la
CLI estarán implementadas en Python.

## Código existente

- `subtitles_bridge_cli.py`: launcher directo e independiente del `cwd`.
- `menu.sh`: wrapper interactivo de la CLI nueva.
- `setup.sh`: instalación portable del entorno sin modificar paquetes del sistema.
- `process_videos.py`: orquestación monolítica del flujo anterior.
- `local_translate_srt.py`: traducción remota del flujo anterior.
- `subtitles_bridge/`: núcleo nuevo con modelos, rutas, discovery, validación
  SRT, FFprobe, planner, resumen previo, transcripción local y remux MKV en
  staging, verificación contractual, publicación atómica, cuarentena segura,
  orquestación inyectable, resultados detallados, reanudación verificada y
  composición de aplicación, diagnóstico portable y observabilidad JSON Lines.
- `tools/normalize_video_mp4/`: utilidad independiente importada para estudiar
  FFprobe, FFmpeg y metadata; no define el contenedor final del nuevo pipeline.

## Documentación

- [`docs/PROJECT.md`](docs/PROJECT.md): objetivo, alcance y decisiones.
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md): preflight, matriz y transacción por
  video.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): límites del núcleo Python y
  dirección de dependencias.
- [`BACKLOG.md`](BACKLOG.md): fases, orden y criterios de aceptación.
- [`tests/README.md`](tests/README.md): alcance de la red de seguridad y fallos
  conocidos reproducidos.

Las decisiones de producto se documentan antes de cambiar comportamiento.
