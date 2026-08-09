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

## Semántica de transcripción P0.5

La etapa `transcribe` se ejecuta únicamente cuando el `BatchPlan` completo es
ejecutable y el `VideoPlan` la marca como `run`. Un plan `skip` no carga Whisper
y un lote o plan `needs-input` falla antes de crear staging. La etapa vuelve a
comprobar que el inventario no tenga ningún subtítulo válido y utiliza
exactamente el índice de audio elegido por el planner.

El SRT generado se escribe como
`staging/<base>.generated.<idioma>.srt`. El idioma detectado forma parte del
nombre para conservar esa metadata durante una reanudación sin archivos
auxiliares. Si staging ya contiene un único candidato válido de una ejecución
interrumpida, se reutiliza sin invocar Whisper. Un candidato inválido o varios
candidatos se tratan como colisión y nunca se sobrescriben.

Whisper no ofrece una selección portable del stream interno de un contenedor.
Por eso P0.5 extrae exclusivamente el audio elegido a un WAV PCM mono de 16 kHz
dentro de staging mediante `ffmpeg -map 0:<stream>`. Ese WAV es temporal, no
forma parte del resultado final y se elimina al terminar o fallar la etapa. La
decodificación temporal no modifica, comprime ni elimina ningún stream de la
fuente; el remux final continuará copiándolos todos en P0.6.

El backend importa `openai-whisper` desde el mismo `sys.executable` que ejecuta
la aplicación, sin resolver un comando global mediante `PATH`. Si falta o está
incompleto, el error incluye el comando de instalación para ese intérprete.
Whisper siempre usa la tarea `transcribe`: detecta el idioma o recibe uno
explícito y produce un único SRT en ese idioma. No ejecuta `translate` ni llama
a servicios remotos. El modelo predeterminado continúa siendo `small`; el
dispositivo se deja en selección automática de Whisper y puede configurarse de
forma explícita, sin fijar siempre CPU o `fp16=False`.

La transcripción tampoco descarga modelos de forma implícita. El modelo debe
ser una ruta local o existir y superar su checksum en el cache de Whisper. Si
falta, la etapa informa cómo precargarlo explícitamente cuando haya red, pero
no inicia una descarga durante el procesamiento.

Después de generar el archivo, el validador SRT de P0.3 debe aprobarlo antes de
devolver el artefacto. Ante cualquier error se propaga una excepción
accionable, se eliminan solo los temporales creados por la etapa y permanecen
intactos el video y los sidecars de entrada.

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

### Semántica de remux P0.6

La etapa `mux` solo se ejecuta cuando el `BatchPlan` completo es ejecutable y
el `VideoPlan` la marca como `run`. Un plan `skip` no inicia FFmpeg; un plan o
lote bloqueado falla antes de crear archivos. P0.6 deja el resultado en
`staging/<base>.subtitled.mkv`: todavía no lo considera verificado, no lo mueve
a `output/` y no archiva ningún insumo.

La ruta de staging es exclusiva. Si ya existe un archivo, directorio o enlace
con ese nombre, la etapa informa una colisión y nunca lo reemplaza ni lo acepta
como válido por mera existencia. P0.7 será responsable de verificar y publicar
una salida temporal.

El comando se construye de forma explícita:

- la fuente es el primer input y se incorpora completa mediante `-map 0`;
- cada SRT externo o generado es un input adicional y se mapea una sola vez;
- los subtítulos embebidos no se vuelven a agregar porque ya forman parte de
  `-map 0`;
- metadata global y capítulos se copian desde la fuente;
- `-c copy` se aplica a todos los streams y nunca existe un fallback de
  recodificación;
- los streams desconocidos también se intentan copiar; si Matroska no puede
  representarlos, FFmpeg debe fallar en lugar de omitirlos silenciosamente;
- idioma y título se asignan a los SRT agregados cuando están disponibles;
- todas las pistas de subtítulos, incluidas las embebidas, pierden únicamente
  la marca `default`; otras disposiciones como `forced` o `hearing_impaired`
  se conservan y Matroska no infiere una nueva pista predeterminada;
- la codificación validada del SRT se entrega a FFmpeg cuando no es UTF-8, sin
  reescribir el sidecar original.

Cuando `transcribe=run`, `mux` exige exactamente el artefacto generado y
validado por P0.5. Cuando `transcribe=skip`, utiliza exactamente los subtítulos
válidos seleccionados por el planner y rechaza un artefacto adicional no
planificado. Un SRT inválido, sin validación o desaparecido nunca se incorpora.

FFmpeg procesa los archivos por streaming: ni el video ni los audios se cargan
completos en memoria. Si el proceso falla o deja una salida parcial o vacía, se
elimina únicamente ese MKV nuevo de staging; el video fuente y todos los SRT
permanecen intactos.

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

### Semántica de verificación y publicación P0.7

`verify` y `publish` respetan el `BatchPlan` completo igual que las etapas
anteriores. Un lote bloqueado falla antes de inspeccionar o crear destinos; una
decisión `skip` no repite la operación. La verificación acepta exclusivamente
`staging/<base>.subtitled.mkv` y los mismos artefactos que P0.6 recibió del
planner o de la transcripción.

El verificador obtiene una nueva inspección FFprobe y exige que el archivo no
cambie de tamaño ni fecha de modificación durante la lectura. La salida debe
ser Matroska y su secuencia de streams debe contener primero, en el mismo orden,
todos los streams de la fuente; después aparecen exactamente los SRT externos
o generados agregados por P0.6. No se admiten streams faltantes ni inesperados.

Por cada stream original se comparan tipo y codec. En audio también deben
coincidir idioma, título y todas las disposiciones. Los subtítulos embebidos
conservan codec, idioma, título y todas sus disposiciones salvo `default`, que
debe estar ausente. Los SRT agregados deben ser `subrip`, conservar idioma y
título cuando eran conocidos y tampoco pueden ser predeterminados.

La metadata estable de la fuente debe aparecer en la salida. Se ignoran
únicamente campos técnicos dependientes del contenedor o regenerados por
FFmpeg, como `encoder`, `major_brand`, `minor_version`, `compatible_brands`,
`handler_name`, `vendor_id`, `creation_time` a nivel de stream y tags de
duración. Los capítulos mantienen orden, cantidad, títulos y metadata, con una
tolerancia de 50 milisegundos para sus tiempos. La duración total admite una
diferencia absoluta máxima de 1 segundo para absorber redondeos de timebase sin
ocultar un truncamiento real.

Una verificación exitosa produce una prueba inmutable con ruta, inspección,
tamaño y `mtime`. La publicación vuelve a comprobar esa identidad antes de
mover el archivo. Si la verificación falla, el MKV permanece en staging para
diagnóstico, pero nunca llega a `output/`; el video y los SRT de entrada siguen
intactos.

La publicación crea `output/` solamente después de verificar, rechaza enlaces
o rutas ocupadas, reserva el destino de forma exclusiva y mueve el MKV con una
operación atómica dentro del mismo workspace. Nunca reemplaza una salida
existente. Al terminar debe existir únicamente
`output/<base>.subtitled.mkv`; el archivado de fuentes continúa fuera de P0.7.

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

### Semántica de archivado P0.8

`archive` se ejecuta solamente cuando el `BatchPlan` completo es ejecutable y
la etapa está marcada como `run`. Una decisión `skip` no crea `trash/` ni mueve
archivos; una decisión `needs-input` falla antes de tocar el filesystem. La
etapa exige una prueba inmutable `PublishedOutput` vinculada con la fuente y con
`output/<base>.subtitled.mkv`; una ruta existente o un plan por sí solos no
autorizan a mover insumos.

La publicación produce esa prueba a partir del `VerifiedOutput` de P0.7 y
conserva el snapshot de tamaño y `mtime`. Antes de archivar se vuelve a comprobar
que el MKV final sigue siendo un archivo regular, no vacío, no es un enlace y
coincide con ese snapshot. Una reanudación puede suministrar una prueba
equivalente para una salida ya verificada; en ese caso el planner mantiene
`transcribe`, `mux`, `verify` y `publish` en `skip`, y ejecuta únicamente
`archive`.

Los insumos exactos son el video fuente y los artefactos con origen `external`
o `generated` registrados en la prueba publicada. Los subtítulos embebidos no
añaden archivos; un SRT inválido, ambiguo, no incorporado o meramente presente
en la carpeta nunca se mueve. Los sidecars conservan su nombre de archivo dentro
de `trash/<base>/`, aunque provinieran de una ubicación reconocida como `sub/` o
`sub_en/`. Por eso dos insumos cuyos nombres colisionen sin distinguir
mayúsculas bloquean el preflight en lugar de elegir o renombrar silenciosamente.

El adaptador valida todos los insumos antes del primer movimiento, crea
`trash/<base>/` de forma exclusiva y reserva también cada destino sin
sobrescribir. Mueve primero los sidecars y deja el video fuente para el final,
de modo que una transacción incompleta no oculte prematuramente el video a
discovery. Los movimientos ocurren dentro del mismo workspace y reemplazan
únicamente las reservas vacías creadas por la propia operación.

Si un movimiento falla, el adaptador intenta restaurar en orden inverso todo lo
que ya había movido y elimina solamente su directorio de destino si volvió a
quedar vacío. El MKV publicado nunca participa del rollback. Un rollback
completo deja los insumos en sus ubicaciones y permite reintentar solo
`archive` con la salida verificada ya existente, sin repetir Whisper ni FFmpeg.
Si también falla la restauración, se conservan los archivos alcanzables y el
directorio parcial, se informa cada ruta pendiente y la colisión queda visible
para resolución manual; nunca se fuerza una sobrescritura para completar el
archivado. Como la salida publicada permanece válida, cualquier fallo del
adaptador se propaga como `ArchivingPartialError` para que P0.9 lo convierta en
estado `partial` y código de salida no exitoso.

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

### Semántica de ejecución y resultado P0.9

El orquestador recibe un `BatchPlan` ya construido y las cinco etapas de
aplicación mediante inyección: `transcribe`, `mux`, `verify`, `publish` y
`archive`. No vuelve a descubrir archivos ni modifica decisiones del planner.
Para cada video ejecutable llama las etapas en ese orden y conserva los
artefactos tipados que conectan una etapa con la siguiente. Una reanudación con
salida ya publicada debe aportar su `PublishedOutput`; el orquestador no acepta
una ruta desnuda como prueba y mantiene las cuatro etapas costosas en `skip`.

Un lote con cualquier ambigüedad o incidencia de discovery no ejecuta ninguna
etapa. Cada video queda como `needs-input` y el resumen conserva tanto las
razones específicas de su plan como los bloqueos globales. En cambio, dentro de
un lote completamente ejecutable, un fallo de un video no impide intentar los
videos independientes restantes.

Cada llamada produce un `StageResult`:

- una decisión `run` que termina correctamente queda `completed` y registra la
  ruta o artefacto producido;
- una decisión `skip` queda `skipped` con la razón original del planner;
- una decisión bloqueada queda `needs-input` sin invocar el backend;
- una excepción queda `failed` con etapa, tipo de excepción, mensaje y rutas
  reales; las etapas posteriores de ese video se registran como omitidas por el
  fallo previo.

El `VideoResult` final aplica reglas no ambiguas:

- `completed`: `archive` terminó y existe su recibo;
- `skipped`: todas las etapas estaban legítimamente omitidas;
- `needs-input`: el preflight bloqueó el lote antes de ejecutar;
- `partial`: existe un `PublishedOutput` válido pero `archive` no terminó;
- `failed`: falló cualquier etapa anterior a la publicación, o el flujo terminó
  sin el artefacto obligatorio de una etapa marcada `run`.

El orquestador captura tanto errores esperados del proyecto como excepciones
inesperadas en su frontera por video, nunca los convierte en éxito nulo y
continúa con el siguiente video seguro. `BatchResult` calcula un estado global,
conteos por estado y un código de salida estable: `0` para éxito o trabajo
legítimamente omitido, `1` si existe algún `failed`, `2` para `needs-input` y
`3` para `partial`. Ante estados mezclados la precedencia es `failed`, luego
`partial` y finalmente `needs-input`. Un lote vacío sin incidencias es
`failed`; uno sin inventarios pero con incidencias permanece `needs-input`.

La frontera de aplicación imprime siempre el resumen final y devuelve ese
código, sin llamar a `sys.exit` dentro del núcleo. El wrapper interactivo solo
anuncia éxito cuando el proceso devuelve `0`; cualquier otro valor se muestra
como ejecución no completada. La definición de argumentos y la independencia
del directorio actual continúan en P1.1-P1.2.

## Observabilidad estructurada P1.6

`--output-format` acepta `text` y `jsonl`. El modo `text` conserva la interfaz
humana predeterminada. El modo `jsonl` reserva stdout para una secuencia de
registros JSON Lines: cada llamada al writer contiene exactamente un objeto
JSON completo y ninguna línea combina texto libre con JSON.

Todos los registros contienen:

- `schema_version: 1`, para evolucionar el contrato de forma explícita;
- `sequence`, entero creciente desde `1` dentro del proceso;
- `event`, nombre estable del evento.

La ejecución normal emite `preflight`, cero o más `stage-started` y
`stage-finished`, y termina con exactamente uno de `batch-result` o `fatal`.
`--preflight` termina con `preflight-result`; `--doctor` utiliza
`doctor-result` o `fatal`. El proceso conserva los códigos `0`, `1`, `2` y `3`
ya documentados: JSON Lines cambia la representación, no la semántica.

Cada evento de etapa identifica `source`, `stage`, estado y ruta objetivo. Una
etapa fallida incluye `error_type` y `error_message`; `transcribe` agrega el
índice del audio elegido. El resultado final vuelve a incluir todos los
resultados de etapa para que la última línea sea autosuficiente, aun cuando un
consumidor no haya conservado los eventos anteriores.

Un video `partial` expone de forma estructurada:

- el MKV publicado que continúa siendo válido;
- el destino de `trash/` que no pudo completarse;
- `archive` como etapa pendiente;
- `--resume` como acción segura de recuperación.

### ETA de trabajo costoso

El conjunto costoso es fijo y explícito: `transcribe`, `mux` y `verify`.
Solamente las decisiones `run` ingresan al cálculo; `skip`, `needs-input`,
`publish` y `archive` nunca aumentan la ETA.

El reloj monotónico es inyectable. Al completar una etapa costosa con duración
multimedia positiva, el estimador aprende segundos reales por segundo de media
para ese tipo de etapa durante el proceso actual. La ETA suma únicamente el
trabajo costoso restante usando muestras del mismo tipo. Si falta la duración
del video o todavía no existe una muestra para alguna etapa restante,
`eta_seconds` es `null` en vez de presentar una precisión falsa. Cada evento
informa también `remaining_expensive_stages`, que sí es exacto desde el plan.

Las muestras no se persisten entre ejecuciones ni contienen nombres de usuario,
contenido de subtítulos o datos remotos. Los tests sustituyen reloj, etapas y
writer para mantener el contrato determinista y offline.

## Entrada ejecutable P1.1

P1.1 conecta el pipeline objetivo mediante una CLI Python mínima. Recibe una
ruta posicional opcional; si se omite utiliza el directorio desde el que el
usuario invocó el comando. La raíz del repositorio solo sirve para localizar el
código, el entorno virtual y los archivos de instalación: nunca reemplaza
silenciosamente la carpeta de videos elegida.

La ejecución tiene una secuencia fija:

1. validar el workspace sin crear rutas administradas;
2. ejecutar discovery con FFprobe y validación SRT;
3. construir y mostrar siempre el preflight completo;
4. entregar el plan al orquestador P0.9;
5. mostrar el resumen final y terminar con su código de salida.

Un plan bloqueado también llega al orquestador para producir un resultado
`needs-input`, pero ninguna etapa con efectos se ejecuta. La CLI no solicita
confirmación para un plan inequívoco: el archivado automático ya forma parte
del contrato confirmado. Tampoco descarga modelos, traduce, recodifica,
sobrescribe ni intenta resolver ambigüedades por aproximación.

La composición predeterminada usa `ffprobe` y `ffmpeg` disponibles en `PATH`,
el modelo local/cacheado `small` de Whisper y los adaptadores de filesystem ya
verificados. Whisper continúa cargándose de forma diferida y solo cuando el
plan marca `transcribe=run`. La selección explícita de audio, modelo,
dispositivo, reanudación y un futuro modo solo-preflight pertenecen a P1.2.

La forma directa es:

```bash
python3 /ruta/al/repositorio/subtitles_bridge_cli.py /ruta/a/videos
```

Cuando el paquete está disponible en el entorno también se admite
`python3 -m subtitles_bridge`. `menu.sh` es únicamente un wrapper: calcula su
propia ubicación y llama la misma CLI con rutas absolutas. `setup.sh` aplica la
misma regla para crear `.venv` e instalar `requirements.txt`, aunque se invoque
desde otro directorio.

## Configuración operativa P1.2

P1.2 mantiene una única ruta posicional y agrega opciones explícitas sin
cambiar el comportamiento seguro predeterminado:

```text
subtitles-bridge [DIRECTORY]
  [--preflight]
  [--audio SOURCE=STREAM_INDEX]...
  [--whisper-model MODEL_OR_PATH]
  [--whisper-device DEVICE]
  [--resume]
```

`DIRECTORY` continúa siendo opcional y, si se omite, representa el `cwd` del
usuario. Las rutas administradas se derivan siempre de ese workspace:
`output/`, `staging/` y `trash/` no se comparten con otra carpeta solo porque
otra aplicación use los mismos nombres. No se agrega un namespace extra; las
reservas exclusivas ya convierten cualquier coincidencia de la ruta final
exacta en un fallo seguro y visible.

### Modo `--preflight`

`--preflight` ejecuta validación del workspace, discovery, resolución de las
opciones explícitas y planificación, imprime el mismo plan de una ejecución
normal y termina sin entregar el lote al ejecutor. Por lo tanto no crea rutas
administradas, no invoca Whisper o FFmpeg y no publica, mueve ni sobrescribe
archivos. FFprobe sí puede ejecutarse porque la inspección read-only es parte
del preflight; con `--resume` también vuelve a inspeccionar la salida existente.

El resultado solo-preflight usa códigos estables: `0` cuando existe al menos un
video y el plan completo está listo, `2` cuando hay decisiones
`needs-input`, y `1` ante un error fatal o una carpeta sin videos. La salida
incluye `Preflight result` y `Exit code` para que pueda usarse en automatización.

### Selección explícita de audio

`--audio SOURCE=STREAM_INDEX` puede repetirse una vez por video. `SOURCE` es el
nombre del archivo directamente dentro del workspace —por ejemplo
`lesson-02.mkv`— o su ruta absoluta; el índice es el número de stream mostrado
por el preflight, no la posición ordinal entre los audios.

La selección se valida contra el video descubierto. Un video desconocido, una
selección duplicada, un índice negativo o un stream inexistente produce un
error accionable sin efectos. La opción solo influye cuando no hay ningún
subtítulo válido y Whisper es necesario; todos los audios se conservan aunque
se transcriba uno solo.

### Configuración diferida de Whisper

`--whisper-model` acepta el nombre de un modelo disponible en el cache local o
la ruta de un checkpoint local; su valor predeterminado sigue siendo `small`.
`--whisper-device` se entrega explícitamente al backend —por ejemplo `cpu`,
`cuda` o `mps`— y, si se omite, Whisper elige el dispositivo.

Estas opciones no validan ni cargan el modelo durante el preflight. Tampoco lo
cargan en una ejecución que reutiliza subtítulos. La ausencia del modelo o un
dispositivo inválido solo puede fallar al comenzar una transcripción realmente
planificada, sin iniciar una descarga automática.

### Reanudación y reemplazo

`--resume` es explícito y se aplica por video. Cuando discovery encuentra
`output/<base>.subtitled.mkv`, la aplicación vuelve a verificar ese archivo
contra el inventario actual y contra los subtítulos externos, embebidos o
generados que debían integrarse. Solo una verificación completa produce una
nueva prueba `PublishedOutput`; entonces el plan marca `transcribe`, `mux`,
`verify` y `publish` como `skip` y ejecuta únicamente `archive`.

Cada sidecar externo o generado incorporado lleva en la metadata interna de su
pista un SHA-256 de los bytes validados. El mux rechaza un sidecar que cambió
después de discovery, la verificación exige que la metadata coincida y el
archivado vuelve a comprobar el archivo actual. Durante `--resume`, el hash del
sidecar que todavía está junto a la fuente o en staging debe coincidir con el
hash de la pista publicada. Así una edición posterior no puede autorizar que se
mueva como si fuera exactamente el archivo integrado. Una salida anterior que
no contiene esta prueba se deja intacta y no es reanudable automáticamente.

Si no existe una salida para un video, `--resume` no inventa una: ese video se
planifica normalmente. Si la salida existente no cumple el contrato, falta el
sidecar necesario para demostrarla, su hash ya no coincide o ya existe
`trash/<base>/`, la reanudación falla sin modificar nada. En particular, una
ruta desnuda o el nombre esperado nunca se aceptan como prueba.

P1.2 no ofrece `--force` ni `--replace`. Sin `--resume`, una salida existente
sigue siendo una colisión; con `--resume`, una salida inválida también se deja
intacta. El reemplazo requiere una política destructiva separada y no se
adivina. Ninguna opción presente o futura autoriza a vaciar, fusionar o
sobrescribir `trash/` silenciosamente.

## Instalación y diagnóstico P1.3

P1.3 agrega `--doctor` como modo independiente de la CLI existente:

```bash
python3 /ruta/al/repositorio/subtitles_bridge_cli.py --doctor
```

No recibe un workspace ni puede combinarse con `--preflight`, `--audio` o
`--resume`. Es read-only: no crea el entorno virtual, no instala paquetes, no
descarga modelos, no inspecciona videos y no modifica `output/`, `staging/` o
`trash/`.

El diagnóstico comprueba, en orden:

1. que el intérprete activo pertenezca a la matriz soportada por P1.4;
2. que `ffmpeg` exista en `PATH` y responda correctamente a `-version`;
3. que `ffprobe` exista en `PATH` y responda correctamente a `-version`;
4. que el modelo configurado de Whisper sea un checkpoint local válido o esté
   presente con checksum correcto en el cache utilizado por la aplicación.

Python, FFmpeg y FFprobe son requisitos para ejecutar el pipeline y una falla
produce `Doctor result: failed` con código `1`. Whisper continúa siendo un
fallback: si el paquete o el modelo local falta, `doctor` informa `warning` y
devuelve `0`, porque todavía pueden procesarse videos que ya poseen algún
subtítulo válido. La salida distingue `ready`, `warnings` y `failed` y muestra
una línea determinista por comprobación.

`doctor` nunca carga el modelo en memoria ni valida el dispositivo solicitado;
solo resuelve y verifica el checkpoint local mediante la misma política del
adaptador productivo. Si falta el modelo, el mensaje explica que la descarga
inicial es explícita y requiere red aceptada por el usuario:

```bash
"/ruta/al/python" -c "import whisper; whisper.load_model('small')"
```

La instalación tampoco descarga ese modelo. `setup.sh` se limita a validar
Python/FFmpeg/FFprobe, crear `.venv`, instalar `requirements.txt` con el Python
del entorno y ejecutar `--doctor`. No instala Homebrew ni paquetes del sistema,
no presupone que `brew` exista y no configura LLVM de forma global. Cuando
falta FFmpeg, muestra una instrucción genérica para el gestor de paquetes de la
plataforma; en macOS puede mencionar `brew install ffmpeg` únicamente si
Homebrew ya está disponible, sin ejecutarlo automáticamente.

## Dependencias reproducibles P1.4

La instalación portable admite CPython 3.10 a 3.13 inclusive. Tanto
`setup.sh` como `--doctor` deben fallar antes de procesar videos cuando el
intérprete queda fuera de ese rango. Las versiones nuevas se incorporan solo
después de validar el flujo y sus dependencias; no se consideran compatibles
por omisión.

`setup.sh` instala exclusivamente `requirements.txt`. Ese archivo contiene la
dependencia directa y fijada del flujo objetivo:

```text
openai-whisper==20250625
```

Whisper conserva la responsabilidad de resolver NumPy, Numba, llvmlite,
PyTorch y sus demás dependencias transitivas según Python y plataforma. El
proyecto no conserva los pins heredados de una instalación Homebrew/LLVM ni
promete un lock transitorio único para macOS, Linux, Windows, CPU y distintos
aceleradores.

El prototipo de traducción remota queda aislado en
`requirements-legacy.txt`, con `deep-translator==1.11.4` fijado solamente para
reproducir su backend Google histórico. No forma parte del setup, del doctor ni
de la CLI principal. Quien decida ejecutarlo debe instalar ese archivo por
separado y aceptar explícitamente el uso de red y el envío de texto al
proveedor. Los backends LibreTranslate y DeepL mencionados por el prototipo no
se declaran como soportados.

Actualizar una dependencia directa exige cambiar su pin, ejecutar la suite
offline completa y repetir el doctor y el smoke test aplicable. Una
reproducción byte a byte de todo el entorno queda fuera de P1.4 hasta contar
con matrices y artefactos por plataforma.

## Checks automáticos P1.5

La puerta de calidad local se ejecuta desde la raíz con:

```bash
python3 tools/check.py
```

El comando falla ante la primera herramienta ausente o comprobación no exitosa
y ejecuta, en orden:

1. `ruff check` sobre el código Python mantenido;
2. `ruff format --check`, sin modificar archivos;
3. `shfmt -d -i 4 -ci` para `menu.sh` y `setup.sh`;
4. ShellCheck para ambos wrappers;
5. `python -m unittest discover -s tests -q`;
6. los smokes de entry point incluidos en la suite.

Las versiones directas quedan fijadas: Ruff `0.15.22` en
`requirements-dev.txt`, ShellCheck `0.11.0` y shfmt `3.13.1`. Estas herramientas
son desarrollo, no runtime: `setup.sh` no las instala y la CLI principal no las
importa.

En el backlog histórico, `inspect` describe la primera etapa read-only del
workflow. La opción pública que la ejecuta y termina después de mostrar el plan
es `--preflight`; P1.5 no agrega un segundo comando sin una diferencia
funcional. El smoke crea un workspace temporal vacío, ejecuta `--preflight`,
espera el fallo estable por lote vacío y verifica que no aparezcan `output/`,
`staging/` o `trash/`. También ejecuta `--help` y exige código `0`. Ninguno de
los dos casos carga Whisper, invoca FFmpeg/FFprobe o accede a la red.

GitHub Actions se ejecuta en cada `push` y `pull_request` con permisos de solo
lectura. Un job Linux corre la puerta de calidad completa. La matriz de
compatibilidad valida macOS y Windows con Python 3.12, y Linux con cada versión
soportada 3.10, 3.11, 3.12 y 3.13. Las imágenes de runner quedan explícitas en
el workflow para que un cambio de sistema sea deliberado. Windows ejecuta la
suite portable completa y omite únicamente las pruebas de los wrappers Bash,
que por contrato pertenecen a macOS/Linux.

## Cierre interactivo P1.7

El flujo recomendado del menú es:

1. **Preparar/verificar instalación** la primera vez o después de una falla de
   dependencias.
2. **Inspeccionar sin cambios** la carpeta para conocer asociaciones,
   colisiones y decisiones pendientes.
3. **Procesar** solamente cuando el plan sea inequívoco.
4. **Reanudar** cuando exista un MKV publicado cuyo archivado quedó incompleto.
5. **Diagnosticar** requisitos sin seleccionar ni modificar un workspace.

Inspección, proceso y reanudación aceptan una ruta escrita o arrastrada al
terminal; Enter utiliza el directorio desde el que se abrió el menú. La opción
de restablecimiento elimina únicamente `.venv` y caches Python del repositorio,
requiere confirmación y se presenta fuera del camino normal.

El wrapper conserva los códigos de la CLI y muestra una explicación distinta:

| Código | Mensaje del menú | Acción sugerida |
| --- | --- | --- |
| `0` | Acción completada. | Revisar el resultado o volver al menú. |
| `1` | Fallo. | Leer la etapa/ruta informada o ejecutar doctor. |
| `2` | Decisión pendiente; no se ejecutó el lote. | Revisar preflight y usar `--audio` si corresponde. |
| `3` | Resultado parcial; el MKV publicado se conserva. | Elegir reanudar después de corregir el archivado. |

La ayuda no presenta la herramienta como convertidor, compresor o gestor de
servidor. Explica que se conservan los streams existentes, que cualquier
subtítulo válido evita Whisper, que el resultado actual es MKV y que solo los
insumos realmente incorporados pasan a la cuarentena reversible `trash/`.

## Contrato candidato P2.1: salida MKV o MP4

Este contrato queda documentado para una posible extensión, pero no está
priorizado ni implementado. El caso de tirones que motivó la evaluación ya era
MP4, por lo que cambiar contenedor no constituye una solución de rendimiento.
La CLI actual continúa generando exclusivamente MKV.

Si una incompatibilidad futura lo justifica, P2.1 agregaría una selección
explícita equivalente a:

```text
--output-container mkv|mp4
```

`mkv` será el valor predeterminado. La elección se aplica a todo el lote para
que las rutas, colisiones y resultados sean deterministas. El preflight siempre
mostrará el contenedor solicitado y el destino derivado antes de crear staging.

### Matriz de compatibilidad

| Inventario | Salida MKV | Salida MP4 |
| --- | --- | --- |
| Video y audio compatibles con copia | Copiar todos. | Copiar todos. |
| Uno o varios audios compatibles | Conservar todos y sus disposiciones. | Conservar todos y sus disposiciones. |
| SRT externo o generado | Agregar como pista seleccionable. | Convertir a `mov_text` y verificar contenido y metadata. |
| Subtítulo embebido de texto representable | Conservar el stream. | Convertir a `mov_text` solo si el contrato puede verificarse. |
| Subtítulo gráfico o estilo no representable | Conservar el stream. | Bloquear MP4; no omitir, quemar ni ejecutar OCR. |
| Adjunto, data stream u otro stream incompatible | Conservar si MKV lo admite. | Bloquear MP4; no descartar. |
| Video o audio que exigiría transcodificación | Copiar si MKV lo admite. | Bloquear MP4; no transcodificar automáticamente. |

La conversión a `mov_text` es la única transformación de codec aceptada en
P2.1 y se limita a subtítulos de texto. El contenido temporal, idioma, título y
carácter no predeterminado de cada pista deben seguir siendo verificables. Si
esa equivalencia no puede demostrarse, MP4 es incompatible para ese video.

### Preflight y ejecución

1. Discovery conserva el inventario completo sin decidir el contenedor.
2. El planner evalúa cada stream contra el contenedor solicitado.
3. Una incompatibilidad conocida queda en `needs-input`, identifica índice,
   tipo y codec y recomienda repetir con `--output-container mkv`.
4. La aplicación no cambia automáticamente de MP4 a MKV: la ruta solicitada es
   parte del resultado esperado y del contrato de automatización.
5. Solo un lote completamente compatible puede iniciar Whisper o FFmpeg.
6. Mux, verificación, publicación y archivado conservan staging, reservas
   exclusivas, ausencia de sobrescritura y rollback existentes.

### Verificación y reanudación

- El verificador exige el contenedor seleccionado y la extensión correcta.
- Todos los streams originales deben estar presentes. Video y audio conservan
  codec, orden, idioma, disposiciones y metadata estable.
- Para MP4, cada subtítulo convertido debe corresponder exactamente a un
  artefacto planificado y continuar seleccionable y no predeterminado.
- `--resume` solo acepta una salida del contenedor solicitado y vuelve a
  verificar el contrato completo antes de autorizar el archivado pendiente.
- Los eventos estructurados de preflight, progreso y resultado identifican el
  contenedor y la ruta final; los códigos de salida existentes no cambian.

### Límite de rendimiento

Remultiplexar MKV a MP4 puede permitir reproducción directa en un cliente que
no acepte MKV, pero deja intacto el codec de video. No soluciona un cliente o
servidor incapaz de decodificar ese codec, perfil o profundidad de bits. P2.1
no introduce H.264/AAC como normalización automática porque eso requeriría una
política de transcodificación, calidad, costo y aceleración separada.

## Red y privacidad

- Whisper se ejecuta localmente y utiliza CPU/GPU del equipo.
- El flujo principal confirmado no necesita traducción remota.
- El prototipo actual todavía contiene un backend de Google mediante
  `deep-translator`; no forma parte del camino objetivo mínimo.
- Si en el futuro se agrega traducción opcional, deberá informar antes de usar
  red o enviar texto a terceros.

## Decisiones confirmadas

- MP4 y MKV son entradas equivalentes para el usuario.
- MKV es la salida predeterminada por su flexibilidad de streams.
- MP4 permanece como posibilidad no priorizada y no se utiliza como reparación
  genérica de tirones.
- No se recodifica ni descarta contenido del original.
- La única excepción P2.1 es convertir subtítulos de texto a `mov_text` para
  representarlos dentro de MP4; audio y video siempre se copian.
- Todos los audios se conservan.
- Las pistas de audio se preservan como parte del original, pero agregar,
  buscar o administrar audios no forma parte del objetivo del producto.
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
