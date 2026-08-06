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

El contrato funcional todavía no está conectado a un único comando de extremo
a extremo. Ya están completas las fases P0.1-P0.9: el núcleo posee inventario,
planner, transcripción local como fallback, remux, verificación, publicación,
cuarentena, orquestación por lote, resumen y códigos de salida. Sin embargo, el
comando de procesamiento actual sigue siendo un prototipo anterior que:

- procesa únicamente MP4;
- genera un SRT inglés con Whisper;
- lo traduce al español mediante Google;
- no compone aún estas etapas nuevas desde una CLI de argumentos.

Por tanto, el menú actual no debe interpretarse como la experiencia final ni
usarse todavía para confiarle el movimiento de archivos importantes.
Sus errores ya se propagan y el menú solo anuncia éxito con código `0`, pero su
flujo funcional continúa siendo el legado.

La siguiente fase, P1.1, creará el entry point Python independiente del
directorio actual y comenzará a conectar el núcleo ya implementado.

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

## Requisitos previstos

- Python 3.10 o posterior;
- FFmpeg y FFprobe;
- OpenAI Whisper para el caso sin subtítulos;
- macOS como primera plataforma validada.

El núcleo se mantendrá portable a Linux y Windows. Los scripts shell podrán
facilitar la instalación o el uso interactivo, pero la lógica principal y la
CLI estarán implementadas en Python.

## Código existente

- `menu.sh`: menú interactivo del prototipo.
- `setup.sh`: instalación del entorno actual.
- `process_videos.py`: orquestación monolítica del flujo anterior.
- `local_translate_srt.py`: traducción remota del flujo anterior.
- `subtitles_bridge/`: núcleo nuevo con modelos, rutas, discovery, validación
  SRT, FFprobe, planner, resumen previo, transcripción local y remux MKV en
  staging, verificación contractual, publicación atómica, cuarentena segura,
  orquestación inyectable y resultados detallados; todavía no posee el entry
  point final que componga el pipeline completo.
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
