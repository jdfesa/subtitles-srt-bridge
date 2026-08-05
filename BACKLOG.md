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

### [ ] P0.2 Crear un núcleo Python modular

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

### [ ] P0.3 Implementar inventario y asociación conservadora

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

### [ ] P0.4 Implementar el planner y el resumen previo

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

### [ ] P0.5 Generar un subtítulo solo como fallback

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

### [ ] P0.6 Empaquetar en MKV copiando todos los streams

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

### [ ] P0.7 Verificar y publicar atómicamente

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

### [ ] P0.8 Archivar automáticamente en `trash/`

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

### [ ] P0.9 Propagar fallos y resumir el lote

Hacer que la CLI represente correctamente el resultado de uno o varios videos.

**Criterios de aceptación**

- Cada video termina como `completed`, `skipped`, `needs-input`, `partial` o
  `failed`.
- El resumen muestra etapas ejecutadas, omitidas y fallidas.
- `failed` o `partial` produce código de salida distinto de cero.
- Los mensajes muestran rutas y excepciones reales.
- El menú nunca anuncia éxito si la CLI falló.

## P1 - Operación y mantenibilidad

### [ ] P1.1 Hacer scripts independientes del directorio actual

- Resolver la raíz desde la ubicación del script.
- Mantener shell como wrapper de macOS/Linux, no como núcleo obligatorio.
- Proveer una CLI Python utilizable directamente y apta para automatización.

### [ ] P1.2 Definir configuración mínima de la CLI

- Ruta de entrada y modo de preflight.
- Modelo y dispositivo de Whisper cuando se necesiten.
- Selección de audio ante múltiples candidatos.
- Semántica por etapa para reanudación o reemplazo.
- Ninguna opción de fuerza puede sobrescribir silenciosamente `trash/`.

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

1. Cerrar y revisar esta documentación. **Fase actual.**
2. Crear pruebas de caracterización y regresión (P0.1).
3. Crear el esqueleto modular mínimo (P0.2).
4. Implementar preflight y planner bajo pruebas (P0.3-P0.4).
5. Implementar Whisper como fallback (P0.5).
6. Implementar remux MKV, verificación y publicación (P0.6-P0.7).
7. Implementar cuarentena automática y resumen transaccional (P0.8-P0.9).
8. Ejecutar P1 en incrementos pequeños.
9. Repriorizar P2 solamente con evidencia de uso.
