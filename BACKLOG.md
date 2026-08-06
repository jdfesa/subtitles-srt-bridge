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

### [ ] P1.3 Robustecer instalación y diagnóstico

- Verificar Python, FFmpeg y FFprobe.
- No asumir que Homebrew existe.
- Explicar la descarga inicial del modelo Whisper.
- Añadir un comando `doctor` o equivalente.
- Validar primero macOS sin introducir dependencias exclusivas en el núcleo.

### [ ] P1.4 Definir dependencias reproducibles

- Fijar o restringir dependencias directas.
- Documentar versiones de Python soportadas.
- Separar dependencias del flujo principal de backends opcionales o legados.
- Eliminar dependencias de traducción si dejan de tener un uso confirmado.

### [ ] P1.5 Agregar checks automáticos

- Formato y lint de Python y shell.
- Pruebas en cada cambio mediante CI.
- Smoke test de `--help` y `inspect` sin modelos ni red.
- Validación nativa en macOS y luego Linux/Windows.

### [ ] P1.6 Mejorar observabilidad

- Mensajes consistentes y salida apta para automatización.
- ETA basada solo en etapas costosas realmente ejecutadas.
- Diagnóstico explícito de stream, archivo y etapa que falló.
- Registro suficiente para auditar un resultado `partial`.

## P2 - Evaluar solo con alcance confirmado

### [ ] P2.1 Ofrecer salida MP4 opcional

Evaluar MP4 solo si aporta compatibilidad concreta. Nunca debe recodificar o
descartar streams de forma implícita. Si la fuente no es compatible con un
remux sin pérdida, la opción debe fallar o requerir una política separada.

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
   **P1.2 completado; siguiente fase: P1.3.**
9. Repriorizar P2 solamente con evidencia de uso.
