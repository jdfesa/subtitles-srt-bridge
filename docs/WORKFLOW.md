# Flujo funcional

Este documento define cómo la CLI inspecciona, planifica, empaqueta, verifica y
archiva cada video. Es el contrato funcional previo a la implementación.

## Principios

1. **Reutilizar antes de generar.**
2. **Generar únicamente cuando no existe ningún subtítulo válido.**
3. **Incorporar todos los subtítulos asociados, cualquiera sea su idioma.**
4. **Copiar streams; no comprimir, recodificar ni descartar.**
5. **Planificar antes de modificar archivos.**
6. **Verificar antes de publicar y archivar.**
7. **Mover a `trash/`; nunca eliminar ni sobrescribir.**

La CLI no pregunta hechos que pueda observar. Inspecciona archivos y streams,
muestra el plan y pregunta solamente ante una asociación ambigua, una elección
de audio no resoluble o una colisión de salida.

## Entradas

- Una carpeta elegida por el usuario.
- Búsqueda no recursiva de videos `.mp4` y `.mkv`.
- SRT externos junto al video o en ubicaciones de subtítulos reconocidas.
- Pistas de subtítulos embebidas, detectadas mediante FFprobe.
- Uno o más streams de video y audio.

Las carpetas administradas `output/` y `trash/` nunca se consideran fuentes de
una nueva ejecución.

Las ubicaciones externas reconocidas son:

- el nivel principal de la carpeta de entrada;
- un nivel dentro de `sub/`, `subs/` o `subtitles/`;
- un nivel dentro de carpetas `sub_<idioma>`, por ejemplo `sub_en/`, `sub_es/`
  o `sub_por/`.

No se recorren otras carpetas ni niveles adicionales. Una carpeta
`sub_<idioma>` aporta metadata de idioma, pero nunca reemplaza la asociación
obligatoria por nombre base.

## Etapa 1: preflight

Antes de modificar archivos, la CLI construye un inventario independiente por
video:

1. Detecta el contenedor y todos sus streams mediante FFprobe.
2. Registra codec, idioma, título y disposición de cada stream.
3. Conserva la lista completa de videos, audios, subtítulos, datos, capítulos y
   adjuntos que deban copiarse.
4. Busca SRT externos que puedan asociarse de forma conservadora.
5. Valida que cada SRT tenga bloques legibles.
6. Clasifica idioma y título cuando la metadata o el nombre lo permitan.
7. Detecta candidatos ambiguos sin seleccionarlos silenciosamente.
8. Busca un resultado previo y valida si ya cumple el contrato.
9. Comprueba anticipadamente colisiones en `output/` y `trash/`.
10. Muestra un plan sin generar, mover ni sobrescribir archivos.

Ejemplo con subtítulos existentes:

```text
Video: lesson-01.mp4
Audio: eng (default), spa
Subtitles found:
  - lesson-01.en.srt (eng)
  - lesson-01.es.srt (spa)
Output: output/lesson-01.subtitled.mkv (missing)

Plan:
  [skip] Whisper
  [run]  Copy every source stream and add 2 subtitle tracks
  [run]  Verify output
  [run]  Move source and 2 used sidecars to trash/lesson-01/
```

Ejemplo sin subtítulos:

```text
Video: lesson-02.mkv
Audio: eng (default)
Subtitles found: none

Plan:
  [run]  Generate one English SRT with Whisper
  [run]  Copy every source stream and add the generated subtitle
  [run]  Verify output
  [run]  Move source and generated sidecar to trash/lesson-02/
```

## Asociación de subtítulos externos

La asociación se realiza por video y debe ser conservadora, especialmente en
carpetas con varios archivos.

Coincidencias reconocibles para `lesson-01.mp4` incluyen:

- `lesson-01.srt`;
- `lesson-01.en.srt`, `lesson-01.eng.srt`, `lesson-01.english.srt`;
- `lesson-01.es.srt`, `lesson-01.spa.srt`, `lesson-01.spanish.srt`;
- sufijos equivalentes de otros idiomas;
- nombres equivalentes dentro de ubicaciones de subtítulos reconocidas.

Reglas:

- el nombre base del video debe coincidir con el del SRT;
- también se aceptan sufijos separados por `.`, `_` o `-`, por ejemplo
  `lesson-01.en.srt`, `lesson-01_forced.srt` o `lesson-01-commentary.srt`;
- el primer token del sufijo debe ser un idioma o calificador reconocido; un
  sufijo numérico o arbitrario no se adivina como metadata;
- no se asocia por similitud aproximada;
- todos los candidatos inequívocos se incorporan, incluso si comparten idioma;
- un idioma desconocido no impide incorporar una asociación inequívoca: la
  pista puede etiquetarse como `und` y conservar un título descriptivo;
- si `lesson-01.srt` no puede distinguirse de candidatos para varios videos, la
  CLI solicita una selección;
- un SRT inválido se informa y no se mueve a `trash/`;
- ningún SRT se reclama para más de un video.

Si un nombre puede corresponder a varios videos —por ejemplo `lesson.en.srt`
cuando existen `lesson.mp4` y `lesson.en.mkv`— se registra como ambiguo y no se
incluye en ningún inventario. Un SRT sin candidatos queda como no asociado y
tampoco se incorpora silenciosamente.

P0.3 es completamente read-only: no crea `output/`, `trash/` ni staging; no
renombra, mueve o reescribe SRT; y no ejecuta Whisper o FFmpeg.

## Semántica del planner P0.4

El planner consume el resultado de discovery y produce decisiones para
`transcribe`, `mux`, `verify`, `publish` y `archive`. No ejecuta ninguna de esas
etapas ni modifica el filesystem. Cada decisión es `skip`, `run` o
`needs-input` y contiene una razón apta para mostrar al usuario.

Las reglas de bloqueo son conservadoras:

- un SRT inválido queda excluido, pero no bloquea; si no existe ningún
  subtítulo válido, se planifica la transcripción;
- un SRT ambiguo bloquea todos los videos candidatos antes de ejecutar trabajo
  costoso;
- una incidencia no asociada o una inspección fallida permanece visible y hace
  que el lote completo requiera atención;
- si falta una selección inequívoca de audio, el video completo queda en
  `needs-input`;
- cualquier decisión `needs-input` hace que el plan no sea ejecutable.

La mera existencia de `output/<base>.subtitled.mkv` nunca demuestra que la
salida sea válida. Una salida existente sin una verificación explícita es una
colisión. Cuando un llamador entrega una salida ya verificada, el planner omite
`transcribe`, `mux`, `verify` y `publish`, y conserva únicamente el archivado
pendiente para permitir una reanudación segura.

Un destino `trash/<base>/` existente también es una colisión y se detecta antes
de Whisper o FFmpeg. Si dos videos del mismo lote derivan la misma salida o el
mismo destino de cuarentena, ambos quedan en `needs-input`. La comparación de
destinos ignora mayúsculas para proteger primero los filesystems habituales de
macOS, donde nombres que difieren solo por capitalización suelen colisionar.

P0.4 solo representa estas decisiones y genera el resumen previo. La
verificación concreta de una salida, la ejecución de etapas y la resolución
interactiva de elecciones pertenecen a fases posteriores.

## Matriz de planificación

| Subtítulos externos válidos | Subtítulos embebidos válidos | Trabajo mínimo |
| --- | --- | --- |
| Uno o más | Cualquier cantidad | Omitir Whisper; conservar los embebidos y agregar todos los externos. |
| Ninguno | Uno o más | Omitir Whisper; conservar todas las pistas embebidas. |
| Ninguno | Ninguno | Generar un único SRT desde el audio seleccionado y agregarlo. |

La decisión se toma por existencia de cualquier subtítulo válido, no por un par
obligatorio inglés/español. No se traduce para completar idiomas ausentes.

## Selección de audio para Whisper

Esta etapa solo existe cuando el inventario no contiene ningún subtítulo:

1. Si hay un único audio, se utiliza ese stream.
2. Si hay varios y exactamente uno es predeterminado, se utiliza el
   predeterminado.
3. Si la metadata identifica de forma inequívoca el audio solicitado por el
   usuario, se utiliza ese stream.
4. Si quedan varios candidatos, el preflight pregunta cuál transcribir.
5. Whisper detecta o recibe el idioma hablado y genera un solo SRT en ese mismo
   idioma.

Todos los streams de audio se conservan en el MKV final, incluido cualquiera
que no haya sido elegido para transcripción.

## Etapas idempotentes

El pipeline se divide en responsabilidades pequeñas:

1. `inspect`: inventariar entradas y artefactos previos.
2. `plan`: decidir qué etapas ejecutar y detectar ambigüedades o colisiones.
3. `transcribe`: generar un SRT únicamente si no existe ninguno.
4. `mux`: construir un MKV temporal copiando todos los streams.
5. `verify`: comprobar que el resultado satisface el contrato.
6. `publish`: mover atómicamente el resultado verificado a `output/`.
7. `archive`: mover automáticamente los insumos consumidos a `trash/`.

Cada etapa debe poder probarse sin Whisper, FFmpeg, red ni movimientos reales
mediante dobles y fixtures pequeños.

## Empaquetado MKV sin recodificación

El resultado se escribe primero en staging y usa MKV porque acepta de manera
flexible múltiples streams y subtítulos.

El comando FFmpeg debe:

- mapear todos los streams del original;
- copiar sin recodificar video y audio;
- conservar subtítulos embebidos, capítulos, metadata y otros streams
  compatibles;
- agregar cada SRT externo o generado como pista separada;
- asignar idioma y título cuando se conozcan;
- marcar todas las pistas de subtítulos como no predeterminadas;
- fallar antes que recodificar o eliminar silenciosamente un stream.

Remultiplexar no comprime el video. El tamaño puede cambiar levemente por la
estructura del contenedor, pero los payloads de audio y video mantienen sus
codecs y calidad.

## Verificación

Antes de considerar exitoso un video, la CLI comprueba al menos:

- FFmpeg terminó con código `0`;
- el MKV temporal existe y no está vacío;
- todos los streams de video del original están presentes;
- todos los streams de audio del original están presentes;
- los codecs de video y audio coinciden con los del original;
- idiomas y disposiciones de audio coinciden con los del original;
- todas las pistas embebidas que debían preservarse están presentes;
- cada subtítulo externo incorporado aparece como una pista diferenciada;
- idioma y título coinciden cuando eran conocidos;
- ninguna pista de subtítulos está marcada como predeterminada;
- capítulos y metadata requeridos se conservaron;
- la duración coincide con la fuente dentro de una tolerancia documentada;
- el archivo puede abrirse nuevamente con FFprobe.

Solo un resultado que supere estas comprobaciones puede publicarse.

## Publicación y `trash/`

Después de verificar:

1. El MKV de staging se publica atómicamente como
   `output/<base>.subtitled.mkv`.
2. Se crea `trash/<base>/` sin reemplazar contenido existente.
3. Se mueve automáticamente el video original.
4. Se mueven únicamente los SRT externos o generados que fueron incorporados.
5. Se deja intacto cualquier archivo ambiguo, inválido o no utilizado.

`trash/` es una zona de cuarentena administrada por el proyecto:

- el movimiento es automático porque es reversible;
- el programa nunca vacía `trash/` ni elimina definitivamente archivos;
- el usuario revisa y elimina manualmente su contenido cuando lo considere;
- ninguna ruta existente se sobrescribe;
- una colisión o fallo de movimiento se informa como resultado parcial;
- el MKV verificado permanece válido si el archivado falla;
- jamás se mueve un insumo antes de publicar una salida verificada.

Las pistas embebidas no tienen sidecar que mover: permanecen dentro del original
archivado y del MKV final.

## Archivos existentes y reanudación

- Una salida existente no se acepta solo por su nombre: debe verificarse.
- El staging usa nombres exclusivos y nunca reemplaza el original.
- Sin una opción explícita de reemplazo, una salida o destino de `trash/`
  existente se considera una colisión.
- Un fallo antes de verificar conserva todos los insumos en su ubicación.
- Un fallo de archivado posterior a la publicación se reporta como parcial y
  debe poder reanudarse sin volver a ejecutar Whisper o FFmpeg.
- La semántica de cualquier futuro `--force` debe definirse por etapa; nunca
  habilita sobrescrituras silenciosas dentro de `trash/`.

## Errores y resumen del lote

Cada video termina en uno de estos estados:

- `completed`: salida verificada e insumos archivados;
- `skipped`: ya estaba completo y verificado;
- `needs-input`: existe una ambigüedad que requiere decisión;
- `partial`: salida válida publicada, pero archivado incompleto;
- `failed`: no pudo producirse o verificarse la salida.

El resumen distingue estos estados. Cualquier `failed` o `partial` produce un
código de salida distinto de cero y un mensaje accionable.

## Red y privacidad

- Whisper se ejecuta localmente y utiliza CPU/GPU del equipo.
- El flujo principal confirmado no necesita traducción remota.
- El prototipo actual todavía contiene un backend de Google mediante
  `deep-translator`; no forma parte del camino objetivo mínimo.
- Si en el futuro se agrega traducción opcional, deberá informar antes de usar
  red o enviar texto a terceros.

## Decisiones confirmadas

- MP4 y MKV son entradas equivalentes para el usuario.
- MKV es la salida principal por su flexibilidad de streams.
- No se recodifica ni descarta contenido del original.
- Todos los audios se conservan.
- Todos los subtítulos válidos se incorporan como pistas seleccionables.
- La presencia de cualquier subtítulo evita la generación.
- Sin subtítulos se genera uno solo en el idioma hablado.
- No existe traducción automática obligatoria.
- Ningún subtítulo queda seleccionado por defecto.
- El original y los sidecars usados se mueven automáticamente a `trash/` solo
  después de publicar un resultado verificado.
- `trash/` nunca se vacía ni se sobrescribe desde el programa.

## Ambigüedades que requieren interacción

- varios audios sin un candidato inequívoco para Whisper;
- un SRT que podría pertenecer a más de un video;
- una ruta de salida o de `trash/` ya ocupada;
- metadata contradictoria entre nombre, carpeta y stream.

Estas condiciones se detectan durante el preflight. No deben descubrirse
después de iniciar Whisper, FFmpeg o movimientos.
