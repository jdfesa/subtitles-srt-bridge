# Backlog

Plan incremental actualizado a partir de la revisión del repositorio y de las
decisiones funcionales confirmadas el 2026-08-05.

## Convenciones

- **P0:** necesario para confiar en el flujo principal.
- **P1:** necesario para mantenerlo y operarlo con previsibilidad.
- **P2:** mejora opcional; se implementa solo con una necesidad concreta.
- Cada fase debe producir un cambio pequeño, revisable y validado antes de
  comenzar la siguiente.
- Los ítems marcados representan documentación terminada, no implementación.

## Fase 0 - Cerrar el contrato antes de programar

### [x] P0.0 Documentar el flujo confirmado

Definir con precisión que el producto administra subtítulos, no normaliza ni
traduce video de forma obligatoria.

**Decisiones documentadas**

- MP4 y MKV son entradas iniciales equivalentes para el usuario.
- El resultado principal es un MKV nuevo.
- Audio, video y demás streams se copian; no se comprimen ni descartan.
- Se incorporan todos los subtítulos válidos asociados, cualquiera sea su
  idioma.
- Whisper se ejecuta solamente cuando no existe ningún subtítulo válido.
- Sin subtítulos se genera uno en el idioma hablado; no se completa un par de
  idiomas mediante traducción automática.
- El resultado se verifica antes de publicarse.
- Después de verificar, el original y los sidecars usados se mueven
  automáticamente a `trash/` sin sobrescribir ni borrar definitivamente.
- El núcleo será Python modular; shell puede actuar como wrapper.

**Fuente de verdad**

- [`docs/PROJECT.md`](docs/PROJECT.md)
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md)

## P0 - Implementar el flujo confiable por fases

### [x] P0.1 Crear la red de seguridad de pruebas

Agregar una suite determinista y offline antes de refactorizar el prototipo o
la utilidad FFmpeg importada.

**Criterios de aceptación**

- Existe un único comando documentado para ejecutar la suite.
- Whisper, FFprobe, FFmpeg y filesystem se sustituyen con dobles en unit tests.
- Se caracterizan las funciones puras y la construcción de comandos que se
  vayan a reutilizar.
- Se reproducen los fallos actuales relevantes: resolución de Whisper, códigos
  de salida ambiguos, mensajes sin interpolar y uso inseguro de archivos.
- Los fixtures multimedia end-to-end son mínimos y se generan durante la
  prueba; no se incorporan binarios grandes.

**Resultado inicial**

- 29 pruebas offline con `unittest`.
- 12 `expectedFailure` documentan defectos reproducidos del prototipo sin
  ocultarlos ni impedir que la red de seguridad se ejecute.
- No se modificó comportamiento productivo en esta fase.

### [x] P0.2 Crear un núcleo Python modular

Separar responsabilidades antes de incorporar el nuevo comportamiento, sin
crear un framework innecesario.

**Módulos previstos**

- descubrimiento de videos y sidecars;
- modelos de streams, inventario, plan y resultado;
- inspección mediante FFprobe;
- asociación y validación de SRT;
- adaptador de Whisper;
- construcción y ejecución de FFmpeg;
- verificación y publicación;
- archivado en `trash/`;
- CLI y resumen del lote.

**Criterios de aceptación**

- La lógica principal no depende de `menu.sh` ni del directorio de trabajo.
- Las dependencias externas se inyectan o aíslan detrás de adaptadores.
- No se concentra el nuevo pipeline en un único script monolítico.
- El prototipo existente queda protegido o reemplazado gradualmente bajo
  pruebas.

**Resultado**

- El paquete `subtitles_bridge/` define modelos inmutables, errores, política de
  rutas y puertos tipados sin dependencias externas.
- La arquitectura y sus límites están documentados en
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- Se agregaron 21 pruebas del núcleo; la suite completa ejecuta 50 casos y
  conserva los 12 defectos legados como `expectedFailure`.
- Los scripts productivos existentes permanecen sin cambios.

### [x] P0.3 Implementar inventario y asociación conservadora

Construir el preflight por video sin modificar archivos.

**Criterios de aceptación**

- Descubre `.mp4` y `.mkv` de la carpeta principal, sin recursión.
- Ignora `output/`, `trash/` y staging.
- FFprobe inventaría todos los streams, capítulos y metadata relevantes.
- Encuentra SRT externos y subtítulos embebidos.
- Asocia por nombre base; nunca por similitud aproximada.
- Permite varios subtítulos, incluso varios del mismo idioma.
- Distingue `valid`, `invalid` y `ambiguous`.
- Un idioma desconocido puede etiquetarse `und` sin perder un sidecar asociado
  de forma inequívoca.
- Ningún archivo se asigna a dos videos.
- Las ambigüedades se detectan antes de ejecutar herramientas costosas.

**Resultado**

- Discovery read-only de MP4/MKV del nivel principal y SRT de ubicaciones
  reconocidas.
- Adaptador FFprobe inyectable que conserva streams, disposiciones, metadata,
  propiedades escalares, capítulos, formato y duración.
- Validador SRT para LF, CRLF, UTF-8/BOM, UTF-16, CP1252, texto multilínea y
  errores estructurales accionables.
- Asociación exacta con ambigüedades, metadata contradictoria y archivos no
  asociados representados sin adivinanzas.
- 32 pruebas nuevas; la suite completa ejecuta 82 casos y mantiene los 12
  defectos legados como `expectedFailure`.
- Ninguna operación de P0.3 crea, modifica, renombra o mueve archivos.

### [x] P0.4 Implementar el planner y el resumen previo

Transformar el inventario en una lista explícita de etapas por video.

**Criterios de aceptación**

- Con uno o más subtítulos válidos, omite Whisper.
- Conserva todas las pistas embebidas y agrega todos los sidecars válidos.
- Sin subtítulos, planifica una única transcripción.
- Selecciona el único audio o el único predeterminado; con varios candidatos
  solicita una decisión.
- Detecta salidas ya válidas y colisiones antes de modificar archivos.
- Muestra `skip`, `run` y `needs-input` por etapa y video.
- La matriz completa se prueba sin Whisper ni FFmpeg reales.

**Resultado**

- Planner puro por video y lote para `transcribe`, `mux`, `verify`, `publish` y
  `archive`.
- Selección automática del único audio o del único predeterminado, con
  elecciones explícitas y bloqueos accionables para los demás casos.
- Conservación explícita de todos los subtítulos válidos y generación prevista
  solamente cuando no existe ninguno.
- Colisiones de salida, `trash/` y destinos compartidos detectadas antes de
  cualquier etapa costosa; una salida solo se reutiliza si el llamador la marca
  como verificada.
- Resumen determinista por lote y video con `skip`, `run` y `needs-input`.
- 12 pruebas nuevas; la suite completa ejecuta 94 casos y mantiene los 12
  defectos legados como `expectedFailure`.
- P0.4 no ejecuta Whisper, FFmpeg, publicación ni movimientos.

### [x] P0.5 Generar un subtítulo solo como fallback

Corregir la resolución de Whisper y encapsular la transcripción.

**Criterios de aceptación**

- Usa Whisper desde el mismo entorno que `sys.executable` o informa cómo
  reparar una instalación incompleta.
- Nunca ejecuta Whisper si existe cualquier subtítulo válido.
- Transcribe únicamente el stream de audio elegido por el planner.
- Detecta o utiliza el idioma hablado y genera un solo SRT en ese idioma.
- Escribe primero en staging y valida el SRT antes de continuar.
- No traduce automáticamente ni requiere red.
- Un fallo devuelve un código no exitoso y no altera insumos.

**Resultado**

- `TranscriptionStage` solo delega cuando el planner marca `transcribe=run`,
  rechaza planes bloqueados y nunca carga Whisper ante un `skip`.
- Extracción FFmpeg inyectable que mapea exclusivamente el índice global del
  audio elegido a un WAV PCM mono de 16 kHz temporal.
- Backend Python de Whisper cargado desde el intérprete activo, siempre con
  `task=transcribe` y sin depender del ejecutable global ni de traducción.
- Modelos locales o cacheados con checksum obligatorio; el procesamiento nunca
  inicia una descarga implícita.
- SRT con idioma detectado en el nombre, validación estructural, reanudación de
  un candidato válido y cero sobrescrituras de staging.
- Los temporales nuevos se limpian ante éxito o fallo; video y sidecars de
  entrada permanecen intactos.
- Todos los fallos se propagan como excepciones de proyecto para que la futura
  CLI los convierta en estado no exitoso; nunca se devuelven como éxito nulo.
- 19 pruebas nuevas; la suite completa ejecuta 113 casos y mantiene los 12
  defectos legados como `expectedFailure`.

### [x] P0.6 Empaquetar en MKV copiando todos los streams

Crear el resultado con FFmpeg sin recodificación ni descarte silencioso.

**Criterios de aceptación**

- Produce `output/<base>.subtitled.mkv` mediante staging.
- Mapea todos los streams de la fuente.
- Copia sin recodificar todos los videos y audios.
- Conserva idiomas, títulos y disposiciones originales de audio.
- Conserva subtítulos embebidos, capítulos, metadata y streams compatibles.
- Agrega todos los SRT externos o generados como pistas separadas.
- Asigna idioma y título cuando se conocen.
- Marca todos los subtítulos como no predeterminados.
- Falla antes que recodificar o descartar un stream incompatible.
- Un video grande no se carga en memoria ni se comprime.
- La construcción del comando tiene pruebas unitarias.

**Resultado**

- `MuxingStage` ejecuta únicamente planes completos con `mux=run`, reúne
  exactamente los subtítulos previstos y exige el artefacto generado por P0.5
  cuando corresponde.
- Constructor FFmpeg puro con `-map 0`, inputs SRT explícitos, metadata y
  capítulos de la fuente, `-copy_unknown` y `-c copy` para impedir cualquier
  recodificación o descarte automático.
- Todos los subtítulos quedan con disposición no predeterminada; Matroska usa
  `default_mode=passthrough`, se conservan otras marcas como `forced` y los SRT
  agregados reciben idioma y título cuando se conocen.
- Los SRT CP1252 y UTF-16 utilizan la codificación detectada por el validador
  sin reescribir los sidecars; los artefactos inválidos o no validados se
  rechazan.
- La salida exclusiva se reserva en staging, FFmpeg trabaja en un MKV hermano
  y solo finaliza el destino después de producir un archivo no vacío. Un fallo
  limpia la reserva y el parcial sin modificar entradas.
- Un smoke test manual con FFmpeg/FFprobe reales confirmó dos audios con
  idiomas, títulos y disposiciones preservados, más subtítulos embebido y
  externo seleccionables con disposición `default=0`.
- 14 pruebas nuevas; la suite completa ejecuta 127 casos y mantiene los 12
  defectos legados como `expectedFailure`.

### [x] P0.7 Verificar y publicar atómicamente

No aceptar una salida por mera existencia o por el código de FFmpeg.

**Criterios de aceptación**

- La salida temporal existe, no está vacía y puede inspeccionarse con FFprobe.
- Cantidad y codecs de video y audio coinciden con la fuente.
- Están presentes las pistas embebidas y externas esperadas.
- Ningún subtítulo está marcado como predeterminado.
- Se comprueban metadata, capítulos y duración según el contrato.
- Solo una salida válida se mueve atómicamente a `output/`.
- Nunca se reemplaza una salida previa sin una política explícita.
- Un fallo conserva el original y todos los sidecars en su ubicación.

**Resultado**

- `OutputContractVerifier` vuelve a inspeccionar el MKV con un `MediaProbe`
  inyectable y exige Matroska, cantidad y orden exactos de streams, tipos,
  codecs, metadata estable, capítulos y duración dentro de tolerancia.
- Audio conserva idioma, título y todas sus disposiciones. Los subtítulos
  embebidos conservan codec, metadata y marcas no predeterminadas; cada SRT
  agregado aparece como una pista `subrip` diferenciada y no predeterminada.
- `VerifiedOutput` vincula fuente, ruta, inspección, subtítulos esperados,
  tamaño y `mtime`; un cambio durante o después de FFprobe invalida la prueba.
- `VerificationStage` y `PublishingStage` respetan el plan completo y nunca
  ejecutan backends ante `skip` o `needs-input`.
- `AtomicOutputPublisher` reserva el destino sin sobrescribir y mueve el MKV
  mediante reemplazo atómico de su propia reserva; un fallo conserva staging y
  limpia únicamente esa reserva.
- Se corrigió P0.6 para eliminar solo la disposición `default` de subtítulos y
  preservar marcas como `forced` y `hearing_impaired`.
- Un smoke test real P0.6→P0.7 confirmó remux, verificación y publicación con
  audio intacto, un subtítulo embebido `forced`, un SRT externo seleccionable,
  fuente y sidecar preservados, y staging retirado después de publicar.
- 17 pruebas nuevas; la suite completa ejecuta 144 casos y mantiene los 12
  defectos legados como `expectedFailure`.

### [x] P0.8 Archivar automáticamente en `trash/`

Mover los insumos consumidos únicamente después de publicar un MKV verificado.

**Criterios de aceptación**

- Crea `trash/<base>/` al final de la transacción.
- Mueve el video original y solo los SRT efectivamente incorporados.
- Un SRT generado también queda disponible en la cuarentena.
- No mueve archivos ambiguos, inválidos o no utilizados.
- Nunca sobrescribe rutas existentes.
- El programa nunca elimina ni vacía `trash/`.
- Una colisión se detecta en preflight.
- Un fallo de archivado conserva el MKV válido, informa estado `partial` y puede
  reanudarse sin repetir Whisper ni FFmpeg.

**Resultado**

- `PublishingStage` produce `PublishedOutput`, una prueba inmutable que vincula
  la salida final con su fuente, subtítulos exactos, inspección, tamaño y
  `mtime`; `archive` rechaza rutas sueltas o snapshots obsoletos.
- `ArchivingStage` respeta el plan completo, mueve únicamente la fuente y los
  SRT externos o generados incorporados, conserva el MKV publicado y nunca
  ejecuta el backend ante `skip` o `needs-input`.
- `TransactionalInputArchiver` valida todos los insumos, reserva de forma
  exclusiva `trash/<base>/` y cada destino, mueve primero sidecars y deja la
  fuente para el final sin copiar archivos grandes en memoria.
- Un fallo restaura en orden inverso lo ya movido y retira únicamente reservas
  propias. Si también falla el rollback, conserva el destino parcial y detalla
  las rutas para revisión manual; ninguna variante sobrescribe o elimina
  contenido útil.
- Los fallos posteriores a una publicación válida se propagan como
  `ArchivingPartialError`. Tras un rollback completo puede reintentarse solo
  `archive`; una salida previamente verificada mantiene las etapas costosas en
  `skip`.
- El planner bloquea antes de ejecutar dos sidecars que al aplanarse en
  `trash/<base>/` compartirían nombre sin distinguir mayúsculas.
- 15 pruebas nuevas; la suite completa ejecuta 159 casos y mantiene los 12
  defectos legados como `expectedFailure`.

### [x] P0.9 Propagar fallos y resumir el lote

Hacer que la CLI represente correctamente el resultado de uno o varios videos.

**Criterios de aceptación**

- Cada video termina como `completed`, `skipped`, `needs-input`, `partial` o
  `failed`.
- El resumen muestra etapas ejecutadas, omitidas y fallidas.
- `failed` o `partial` produce código de salida distinto de cero.
- Los mensajes muestran rutas y excepciones reales.
- El menú nunca anuncia éxito si la CLI falló.

**Resultado**

- `BatchExecutor` conecta mediante inyección `transcribe`, `mux`, `verify`,
  `publish` y `archive`, conserva los artefactos tipados entre etapas y no
  vuelve a descubrir ni alterar el plan.
- Los lotes bloqueados no ejecutan backends; en un lote ejecutable, la
  excepción de un video queda aislada y no impide procesar los videos
  independientes restantes.
- `StageResult`, `VideoResult` y `BatchResult` registran etapas, rutas,
  incidencias y estados `completed`, `skipped`, `needs-input`, `partial` o
  `failed` con mensajes accionables.
- Los códigos de salida son estables: `0` para completado u omitido, `1` para
  fallo, `2` para decisiones pendientes y `3` para salida publicada con
  archivado incompleto.
- La reanudación del archivado exige un `PublishedOutput`; una ruta existente
  sin prueba no evita Whisper, FFmpeg ni verificación.
- La frontera de aplicación imprime un resumen determinista y devuelve el
  código sin terminar el intérprete. El prototipo legado ahora propaga sus
  fallos y `menu.sh` anuncia éxito únicamente ante código `0`.
- 16 pruebas nuevas y una reproducción legada convertida en regresión; la
  suite completa ejecuta 175 casos y conserva 11 defectos legados como
  `expectedFailure`.
- P0.9 no agrega todavía el entry point de argumentos que componga discovery,
  planner, adaptadores y ejecutor; esa integración comienza en P1.1-P1.2.

## P1 - Operación y mantenibilidad

### [x] P1.1 Hacer scripts independientes del directorio actual

- Resolver la raíz desde la ubicación del script.
- Mantener shell como wrapper de macOS/Linux, no como núcleo obligatorio.
- Proveer una CLI Python utilizable directamente y apta para automatización.

**Resultado**

- `WorkspaceApplication` coordina workspace, discovery, planner, preflight y
  el ejecutor P0.9 mediante dependencias inyectadas, sin conocer adaptadores
  concretos.
- `bootstrap.py` construye el grafo predeterminado con FFprobe, FFmpeg,
  Whisper local diferido, verificación, publicación y archivado; construir la
  aplicación no carga modelos ni inicia procesos.
- `subtitles_bridge_cli.py` funciona directamente desde cualquier directorio y
  `python -m subtitles_bridge` reutiliza exactamente la misma frontera.
- La CLI siempre muestra el preflight, ejecuta automáticamente únicamente un
  plan inequívoco y conserva los códigos `0`, `1`, `2` y `3` de P0.9.
- `menu.sh` y `setup.sh` resuelven raíz, `.venv`, launcher y requirements desde
  `BASH_SOURCE[0]`; la carpeta de videos sigue resolviéndose desde el contexto
  del usuario y el menú admite rutas arrastradas con espacios escapados.
- Siete pruebas nuevas cubren composición diferida, CLI directa desde otro
  `cwd`, errores fatales y wrappers shell sin ejecutar herramientas reales. La
  suite completa ejecuta 182 casos con 11 `expectedFailure` legados.
- Un smoke test temporal con FFmpeg/FFprobe reales confirmó video, audio y SRT
  seleccionable no predeterminado en el MKV, más publicación y cuarentena de
  los dos insumos, sin cargar Whisper.
- Las opciones de preflight-only, audio, modelo, dispositivo y reanudación
  permanecen deliberadamente en P1.2.

### [x] P1.2 Definir configuración mínima de la CLI

- Ruta de entrada y modo de preflight.
- Modelo y dispositivo de Whisper cuando se necesiten.
- Selección de audio ante múltiples candidatos.
- Semántica por etapa para reanudación o reemplazo.
- Ninguna opción de fuerza puede sobrescribir silenciosamente `trash/`.

**Contrato documentado antes de implementar**

- `--preflight` será read-only y devolverá `0` si el plan está listo, `2` si
  requiere decisiones y `1` ante fallo fatal o lote vacío.
- `--audio SOURCE=STREAM_INDEX` resolverá elecciones por video sin modificar
  la conservación de todos los streams de audio.
- `--whisper-model` y `--whisper-device` configurarán el backend diferido solo
  cuando la transcripción sea necesaria.
- `--resume` volverá a verificar cada salida existente y solo después aportará
  la prueba que permite ejecutar el archivado pendiente.
- P1.2 no agregará reemplazo ni fuerza: una salida inválida o cualquier ruta
  existente dentro de `trash/` seguirá intacta y bloqueará la operación.

**Resultado**

- La CLI acepta `--preflight`, `--audio SOURCE=STREAM_INDEX` repetible,
  `--whisper-model`, `--whisper-device` y `--resume`; no incorpora `--force` ni
  `--replace`.
- El modo solo-preflight conserva los códigos `0`, `1` y `2` documentados y se
  detiene antes del ejecutor, sin crear `output/`, `staging/` o `trash/`.
- Las elecciones de audio se resuelven contra fuentes directas del workspace,
  rechazan duplicados o índices inexistentes y no cambian la conservación de
  todos los streams.
- `WhisperConfig` llega al adaptador desde el composition root, pero el modelo
  continúa sin cargarse si el plan no ejecuta transcripción.
- `ExistingOutputResumer` vuelve a verificar el contrato completo, reconstruye
  una prueba `PublishedOutput` y permite que el ejecutor omita transcripción,
  remux, verificación de etapa y publicación para ejecutar solo el archivado.
- Cada sidecar validado se vincula con su pista mediante SHA-256 interno; mux,
  verificación, reanudación y archivado rechazan cambios posteriores, sin crear
  un manifest externo ni sobrescribir archivos.
- El descubrimiento de un SRT generado reanudable es compartido con la etapa de
  transcripción y conserva metadata estable entre procesos.
- Once pruebas nuevas cubren opciones, códigos, audio, integridad y
  reconstrucción de pruebas; la suite completa ejecuta 193 casos con 11
  `expectedFailure` legados.
- Un smoke test temporal con FFmpeg/FFprobe reales verificó que preflight no
  crea rutas ni carga un modelo inválido, y que `--resume` revalida un MKV ya
  publicado antes de archivar exactamente el video y su sidecar.

### [x] P1.3 Robustecer instalación y diagnóstico

- Verificar Python, FFmpeg y FFprobe.
- No asumir que Homebrew existe.
- Explicar la descarga inicial del modelo Whisper.
- Añadir un comando `doctor` o equivalente.
- Validar primero macOS sin introducir dependencias exclusivas en el núcleo.

**Contrato documentado antes de implementar**

- `--doctor` será un modo read-only sin workspace y no se combinará con opciones
  de procesamiento.
- Python 3.10+, FFmpeg y FFprobe serán requisitos: una ausencia o ejecución
  fallida devolverá código `1` con instrucciones accionables.
- Whisper y su checkpoint local se diagnosticarán sin cargar ni descargar el
  modelo; su ausencia será `warning` porque el fallback no se necesita cuando
  ya existen subtítulos.
- `setup.sh` no instalará Homebrew ni paquetes del sistema, no configurará LLVM
  globalmente y ejecutará el doctor con el intérprete de `.venv` al finalizar.
- La descarga inicial del modelo se mantendrá explícita, separada de setup y
  acompañada por el comando exacto que requiere red.

**Resultado**

- `--doctor` ejecuta cuatro comprobaciones deterministas: versión del Python
  activo, `ffmpeg -version`, `ffprobe -version` y resolución/checksum del modelo
  Whisper configurado.
- El resumen distingue `ok`, `warning` y `error`; solo un requisito obligatorio
  fallido produce `Doctor result: failed` y código `1`.
- La verificación de Whisper reutiliza el adaptador productivo sin cargar el
  modelo. Un paquete o checkpoint ausente queda como advertencia con el comando
  de instalación o precarga correspondiente.
- `setup.sh` valida requisitos antes de crear `.venv`, controla cada fallo de
  pip, no contiene supuestos de Homebrew/LLVM, ejecuta `--doctor` con el Python
  del entorno y explica que la primera descarga del modelo es manual.
- `menu.sh` propaga e informa el código de setup en lugar de presentar una
  instalación fallida como completada.
- Diez pruebas nuevas cubren diagnóstico, composición, CLI, checkpoint sin
  carga y setup portable; la suite completa ejecuta 203 casos con 11
  `expectedFailure` legados.
- Un smoke test real desde otro `cwd` en macOS confirmó Python 3.12.11, FFmpeg
  8.0.1 y FFprobe
  8.0.1; Whisper ausente se informó como `warning` y el doctor terminó con
  código `0` sin descargar ni crear archivos.

### [x] P1.4 Definir dependencias reproducibles

- Fijar o restringir dependencias directas.
- Documentar versiones de Python soportadas.
- Separar dependencias del flujo principal de backends opcionales o legados.
- Eliminar dependencias de traducción si dejan de tener un uso confirmado.

**Contrato documentado antes de implementar**

- El flujo principal soportará CPython 3.10-3.13; setup y doctor rechazarán
  versiones fuera de la matriz antes de procesar archivos.
- `requirements.txt` fijará `openai-whisper==20250625` como única dependencia
  directa del producto y no conservará pins transitivos específicos de
  Homebrew, LLVM o una sola plataforma.
- Whisper resolverá sus dependencias transitivas según Python y plataforma;
  un lock completo por sistema queda fuera de esta fase.
- `deep-translator==1.11.4` quedará aislado en
  `requirements-legacy.txt` para el prototipo histórico. Setup, doctor y la
  CLI principal no instalarán ni utilizarán traducción remota.
- Cualquier actualización futura del pin directo requerirá suite offline,
  doctor y smoke test antes de publicarse.

**Resultado**

- `requirements.txt` contiene únicamente `openai-whisper==20250625`; Whisper
  vuelve a resolver sus transitivas según Python y plataforma, sin pins
  heredados de Homebrew o LLVM.
- `deep-translator==1.11.4` se trasladó a `requirements-legacy.txt`. El setup y
  la CLI principal no lo instalan ni lo utilizan; su instalación manual queda
  documentada como una operación de red del prototipo histórico.
- Setup y doctor aplican la misma matriz CPython 3.10-3.13 y fallan con un
  mensaje accionable fuera de ella.
- Se agregaron siete pruebas de política, límites de Python, comandos de
  reparación y aislamiento del setup; la suite completa ejecuta 210 casos con
  11 `expectedFailure` legados.
- El doctor real confirmó Python 3.12.11, FFmpeg 8.0.1, FFprobe 8.0.1 y el
  checkpoint local `small`; `pip check` no encontró dependencias rotas.

### [x] P1.5 Agregar checks automáticos

- Formato y lint de Python y shell.
- Pruebas en cada cambio mediante CI.
- Smoke test de `--help` y `inspect` sin modelos ni red.
- Validación nativa en macOS y luego Linux/Windows.

**Contrato documentado antes de implementar**

- `tools/check.py` será la puerta local única y ejecutará Ruff, shfmt,
  ShellCheck, la suite offline y los smokes de CLI sin modificar archivos.
- Ruff `0.15.22` se fijará como dependencia de desarrollo; ShellCheck `0.11.0`
  y shfmt `3.13.1` se fijarán como herramientas externas. Ninguna formará parte
  de `setup.sh` ni de las dependencias productivas.
- Ruff cubrirá el paquete objetivo, entry points, pruebas y herramientas
  mantenidas. Los prototipos legados quedarán fuera del reformateo pero sus
  caracterizaciones continuarán ejecutándose.
- El término histórico `inspect` se validará mediante la opción pública
  existente `--preflight`; no se agregará un alias sin comportamiento distinto.
- Los smokes ejecutarán `--help` y un preflight vacío en subprocess, comprobarán
  sus códigos estables y demostrarán que no crean rutas administradas ni
  requieren Whisper, FFmpeg, modelos o red.
- GitHub Actions correrá en `push` y `pull_request` con permisos read-only. La
  calidad completa usará Linux; la matriz validará Python 3.10-3.13 en Linux y
  Python 3.12 también en macOS y Windows mediante imágenes explícitas.

**Resultado**

- Ruff `0.15.22`, ShellCheck `0.11.0` y shfmt `3.13.1` forman una puerta única
  que valida versiones, formato, lint, suite y smokes sin modificar archivos.
- La línea base aplicó formato determinista al código mantenido y corrigió un
  binding de excepción sin uso, la asignación ambigua de `CDPATH` y los reads
  interactivos que sí debían preservar backslashes.
- Dos smokes de subprocess verifican `--help` y el preflight vacío read-only
  sin rutas administradas ni backends multimedia.
- GitHub Actions define calidad en Ubuntu y seis combinaciones nativas:
  CPython 3.10-3.13 en Linux, 3.12 en macOS y 3.12 en Windows.
- La ejecución Windows omite solamente las pruebas de `menu.sh` y `setup.sh`;
  los wrappers Bash continúan validados en macOS/Linux y el núcleo portable
  ejecuta el resto de la suite nativamente.
- La puerta completa pasa localmente en macOS con 214 pruebas y 11
  `expectedFailure` legados.
- La primera matriz hospedada detectó una aserción de rutas específica de POSIX
  en el test del comando de muxing. La prueba se corrigió para comparar las
  rutas nativas generadas por `pathlib` y conservar el mismo contrato en todas
  las plataformas.
- La ejecución hospedada corregida `31284416484` pasó la puerta de calidad y
  las seis combinaciones de compatibilidad en macOS, Linux y Windows.

### [x] P1.6 Mejorar observabilidad

- Mensajes consistentes y salida apta para automatización.
- ETA basada solo en etapas costosas realmente ejecutadas.
- Diagnóstico explícito de stream, archivo y etapa que falló.
- Registro suficiente para auditar un resultado `partial`.

**Contrato documentado antes de implementar**

- El texto continuará como formato predeterminado y
  `--output-format jsonl` reservará stdout para un objeto JSON completo por
  línea, sin mezclar formatos.
- Cada registro usará `schema_version=1`, `sequence` creciente y eventos
  estables para preflight, etapas, resultado o error fatal.
- `stage-started` y `stage-finished` identificarán fuente, etapa, estado y ruta
  objetivo. Un fallo agregará tipo y mensaje de excepción; la transcripción
  identificará también el stream de audio elegido.
- La última línea será autosuficiente. Un `partial` conservará salida publicada,
  destino de cuarentena, etapa `archive` pendiente y `--resume` como acción de
  recuperación.
- La ETA considerará únicamente decisiones `run` de `transcribe`, `mux` y
  `verify`. Aprenderá tasas con reloj monotónico y duración multimedia de
  etapas completadas en el proceso actual; será `null` si falta una muestra o
  duración, sin inventar constantes.
- El modo JSON Lines conservará los códigos de salida existentes y será probado
  con reloj, stages y writers inyectados, sin FFmpeg, Whisper, red ni efectos
  reales.

**Resultado**

- `--output-format text|jsonl` conserva texto como valor predeterminado y
  permite reservar stdout para registros JSON Lines v1 independientes.
- Preflight, progreso, resultado, doctor y errores fatales utilizan eventos con
  esquema versionado y secuencia creciente; la última línea de una ejecución es
  autosuficiente.
- `BatchExecutor` publica inicio y final de cada etapa ejecutada, mide con reloj
  monotónico inyectable y conserva duración, ruta objetivo, tipo de excepción y
  stream de transcripción dentro de `StageResult`.
- La ETA excluye etapas omitidas, bloqueadas, publicación y archivado. Solo
  utiliza muestras reales por tipo de `transcribe`, `mux` y `verify`, y queda
  `null` cuando no puede estimarse honestamente.
- Un resultado `partial` registra salida publicada, destino de cuarentena,
  `archive` pendiente y `--resume`; el resumen de texto también muestra la
  recuperación y el contexto estructurado disponible.
- Nueve pruebas nuevas cubren esquema, secuencia, ETA, doctor, smoke real,
  tiempos, fallos y recuperación parcial. La suite completa ejecuta 223 casos
  con 11 `expectedFailure` legados y la puerta local completa pasa.

### [x] P1.7 Cerrar la experiencia interactiva y la ayuda

La implementación principal ya es segura, pero el wrapper interactivo solo
expone setup, ejecución directa y limpieza. Preflight, doctor y reanudación
existen en la CLI pero quedan ocultos para quien utiliza `menu.sh`, y la ayuda
no explica códigos de salida ni el flujo recomendado.

**Contrato documentado antes de implementar**

- El menú presentará como acciones principales preparar/verificar instalación,
  inspeccionar una carpeta sin cambios, procesarla, reanudar un archivado
  pendiente, ejecutar diagnóstico y consultar ayuda.
- Restablecer `.venv` y caches seguirá disponible como acción avanzada,
  separada del flujo normal y protegida por confirmación explícita.
- Preflight, procesamiento y reanudación compartirán la misma entrada de ruta,
  incluido drag-and-drop con espacios escapados y directorio actual por defecto.
- El menú interpretará los códigos `0`, `1`, `2` y `3` con mensajes accionables;
  nunca mostrará éxito ante decisiones pendientes o un resultado parcial.
- La ayuda explicará el objetivo único: reutilizar subtítulos válidos o generar
  uno solo cuando no exista ninguno, incorporarlos como pistas seleccionables,
  verificar el MKV y recién entonces archivar insumos en `trash/`.
- Audio existente se preserva, pero agregar o administrar audios, diagnosticar
  streaming y configurar servidores multimedia quedan fuera del menú.
- `--help` incluirá flujo seguro, ejemplos frecuentes, códigos de salida y el
  límite no destructivo; no construirá la aplicación ni requerirá dependencias.
- Las pruebas de shell y CLI cubrirán argumentos, rutas escapadas, estados y
  texto esencial sin ejecutar FFmpeg, Whisper, filesystem productivo o red.

**Implementación local preparada**

- `menu.sh` presenta ocho opciones claras: preparación, preflight read-only,
  procesamiento, reanudación, doctor, ayuda, restablecimiento avanzado y salida.
- Preflight, procesamiento y reanudación comparten el mismo ingreso de ruta y
  preservan drag-and-drop con espacios; doctor no solicita un workspace.
- Los códigos `0`, `1`, `2` y `3` producen mensajes distintos y accionables.
  Un resultado parcial conserva explícitamente el MKV y dirige a reanudación.
- La ayuda del menú explica objetivo, flujo normal y límites de seguridad; la
  opción avanzada confirma que solo elimina `.venv` y caches del repositorio.
- `--help` describe el flujo seguro, ejemplos, códigos y garantías sin construir
  la aplicación ni requerir Whisper, FFmpeg o red.
- Tres pruebas nuevas cubren argumentos exactos de preflight/resume/doctor,
  estados pendientes/parciales y contenido esencial de ayuda. La suite completa
  ejecuta 226 casos con 11 `expectedFailure` legados; Ruff, formato Python,
  sintaxis Bash y `git diff --check` pasan localmente.
- La ejecución hospedada `31325938882` validó la puerta completa, incluidas las
  versiones fijadas de shfmt y ShellCheck, y todas las combinaciones nativas de
  macOS, Linux y Windows.

## P2 - Evaluar solo con alcance confirmado

### [ ] P2.1 Ofrecer salida MP4 opcional

**Pendiente y no priorizado; evaluación documentada el 2026-08-09.**

La evidencia es una biblioteca personal centralizada en Proxmox con un Intel
Core i5-4440: algunos videos 1080p presentan tirones al servirse a una tablet,
aunque los mismos archivos funcionan localmente. El caso inspeccionado ya es
MP4 con H.264, E-AC-3 y 26 subtítulos `mov_text`, por lo que cambiar de MKV a
MP4 no garantiza ni explica una mejora.

La prioridad confirmada continúa siendo obtener subtítulos cuando faltan y
dejarlos seleccionables. El audio existente se conserva, pero agregar, buscar o
administrar pistas de audio no es una funcionalidad objetivo. P2.1 solo se
retomará ante una incompatibilidad concreta de cliente que MP4 pueda resolver
sin transcodificar video o audio.

**Contrato de seguridad si se retoma**

- Agregar `--output-container mkv|mp4`, con MKV predeterminado y una elección
  única para todo el lote.
- Preservar y copiar todos los streams de video y audio, incluidas múltiples
  pistas de audio y sus disposiciones; P2.1 no agrega audios externos.
- Permitir en MP4 únicamente la conversión explícita de subtítulos de texto a
  `mov_text`, conservándolos seleccionables y no predeterminados.
- Bloquear MP4 durante preflight cuando un codec, subtítulo gráfico, estilo,
  adjunto u otro stream no pueda representarse sin pérdida aceptada. Informar
  índice y codec y sugerir MKV, sin fallback automático.
- Derivar, verificar, publicar y reanudar la extensión solicitada con las
  mismas garantías de staging, no sobrescritura, integridad y cuarentena.
- No prometer que cambiar de contenedor elimina los tirones: comparar un caso
  fluido y uno problemático y registrar si el servidor hizo direct play,
  remux o transcodificación. La normalización H.264/AAC queda fuera de P2.1.

**Incrementos posibles, no iniciados**

- [ ] P2.1a Caracterizar compatibilidad MP4 y proteger el flujo MKV existente.
- [ ] P2.1b Modelar contenedor, rutas y bloqueo read-only en planner/preflight.
- [ ] P2.1c Implementar mux, verificación, publicación y resume para MP4.
- [ ] P2.1d Exponer CLI/reporting, completar smokes y validar fixtures reales
  mínimos sin recodificar audio o video.

### [ ] P2.2 Reintroducir traducción opcional

El flujo principal no completa idiomas automáticamente. Si aparece una
necesidad real:

- definir idiomas y backend mediante opciones explícitas;
- informar red, privacidad, límites y credenciales;
- sustituir el parser regex actual antes de utilizarlo;
- cubrir LF, CRLF, archivo sin salto final, etiquetas y multilinea;
- nunca traducir por el solo hecho de faltar un idioma.

### [ ] P2.3 Soportar más entradas

Evaluar `.mov`, otros contenedores, selección recursiva y formatos de subtítulo
adicionales solo después de estabilizar MP4/MKV y SRT.

### [ ] P2.4 Aprovechar hardware disponible

Permitir modelo y dispositivo configurables sin fijar siempre CPU o
`--fp16 False`. Medir antes de optimizar.

### [ ] P2.5 Empaquetar y distribuir

Considerar `pyproject.toml`, entry point, releases, licencia, changelog y un
contenedor opcional solo cuando el uso fuera del clon lo justifique.

## Orden de ejecución

1. Cerrar y revisar esta documentación. **Completado.**
2. Crear pruebas de caracterización y regresión (P0.1). **Completado.**
3. Crear el esqueleto modular mínimo (P0.2). **Completado.**
4. Implementar preflight y planner bajo pruebas (P0.3-P0.4). **Completado.**
5. Implementar Whisper como fallback (P0.5). **Completado.**
6. Implementar remux MKV, verificación y publicación (P0.6-P0.7).
   **Completado.**
7. Implementar cuarentena automática y resumen transaccional (P0.8-P0.9).
   **Completado.**
8. Ejecutar P1 en incrementos pequeños.
   **P1.7 completado; P1 cerrado.**
9. Repriorizar P2 solamente con evidencia de uso.
