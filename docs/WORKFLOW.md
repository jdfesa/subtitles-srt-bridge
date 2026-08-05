# Flujo funcional

Este documento define cómo debe decidir la CLI qué trabajo realizar para cada
video. Es el contrato funcional previo a la implementación.

## Principio principal

La CLI debe **reutilizar primero y generar después**.

Whisper consume tiempo y CPU; la traducción consume tiempo y red. Ninguna de
esas etapas debe ejecutarse cuando ya existe un subtítulo válido que permite
alcanzar el resultado solicitado.

La CLI no debe preguntarle al usuario hechos que puede comprobar por sí misma.
Debe inspeccionar archivos y streams automáticamente, mostrar el plan y
preguntar solo cuando exista ambigüedad, una elección funcional o una acción
destructiva.

## Entradas de la primera versión

- Una carpeta elegida por el usuario.
- Búsqueda no recursiva.
- Videos `.mp4` y `.mkv`.
- Subtítulos externos `.srt` junto al video, en `sub_en/` o en `sub_es/`.
- Pistas de subtítulos ya incorporadas al video, detectadas con FFprobe.

## Etapa 1: preflight

Antes de procesar, la CLI construye un inventario por video:

1. Detecta el video y obtiene sus streams mediante FFprobe.
2. Detecta pistas de audio y sus idiomas.
3. Detecta pistas de subtítulos embebidas y sus idiomas.
4. Busca SRT externos que puedan asociarse con seguridad al video.
5. Valida que cada SRT encontrado tenga bloques legibles.
6. Clasifica los subtítulos como inglés, español o idioma desconocido.
7. Detecta si ya existe un MP4 final y valida sus pistas.
8. Construye y muestra un plan sin modificar archivos.

Ejemplo de resumen:

```text
Video: lesson-01.mkv
Audio: eng (default), spa
English subtitle: found at sub_en/lesson-01.en.srt
Spanish subtitle: missing
Packaged output: missing

Plan:
  [skip] Whisper
  [run]  Translate English -> Spanish
  [run]  Create output/lesson-01.subtitled.mp4
```

## Asociación de subtítulos

La asociación debe ser conservadora, especialmente cuando la carpeta contiene
varios videos.

Coincidencias iniciales reconocidas para `lesson-01.mp4`:

- `lesson-01.en.srt`, `lesson-01.eng.srt`, `lesson-01.english.srt`;
- `lesson-01.es.srt`, `lesson-01.spa.srt`, `lesson-01.spanish.srt`;
- los mismos nombres dentro de `sub_en/` o `sub_es/`.

Reglas:

- El nombre base del video debe coincidir con el del SRT.
- La carpeta `sub_en/` o `sub_es/` puede resolver el idioma aunque el nombre no
  tenga un sufijo de idioma.
- Un archivo como `lesson-01.srt` es ambiguo si no se puede determinar su
  idioma con seguridad; la CLI debe preguntarlo.
- Un SRT no debe asociarse por aproximación a uno de varios videos.
- Si aparecen dos candidatos para el mismo idioma y video, la CLI debe mostrar
  ambos y pedir una selección.

## Matriz de planificación

| Inglés disponible | Español disponible | Trabajo mínimo propuesto |
| --- | --- | --- |
| Sí | Sí | Omitir Whisper y traducción; empaquetar si falta el MP4 final. |
| Sí | No | **Pendiente:** empaquetar solo inglés o traducirlo a español antes de empaquetar. |
| No | No | Ejecutar Whisper en inglés; traducir a español; empaquetar. |
| No | Sí | **Pendiente:** empaquetar solo español, generar inglés con Whisper o traducir español a inglés. |

"Disponible" puede significar un SRT externo válido o una pista embebida cuyo
idioma esté identificado. El tratamiento exacto de pistas embebidas se define
en las decisiones pendientes.

## Etapas independientes

El pipeline debe modelarse como etapas idempotentes:

1. `inspect`: inventariar entradas y construir el plan.
2. `transcribe`: generar el SRT inglés solo cuando haga falta.
3. `translate`: generar el SRT español solo cuando haga falta.
4. `package`: producir el MP4 con las pistas disponibles.
5. `verify`: comprobar el resultado con FFprobe.
6. `cleanup`: actuar sobre el original únicamente bajo una política explícita.

Cada etapa debe poder omitirse sin impedir las posteriores. Por ejemplo, dos
SRT descargados deben poder pasar directamente a `package`.

## Salidas confirmadas

```text
carpeta/
├── lesson-01.mp4                # fuente; también puede ser MKV
├── sub_en/
│   └── lesson-01.en.srt
├── sub_es/
│   └── lesson-01.es.srt
└── output/
    └── lesson-01.subtitled.mp4
```

- Los dos SRT se conservan como archivos.
- El MP4 final contiene pistas `eng` y `spa` para VLC cuando ambos idiomas están
  disponibles.
- Ningún subtítulo queda seleccionado por defecto.
- Se conservan todas las pistas de audio.
- Si puede identificarse una pista de audio inglesa, se marca como default.
- El empaquetado no debe quemar texto sobre el video.
- Streams compatibles deben copiarse; solo se convierten los incompatibles con
  el contenedor MP4.

## Verificación del MP4 final

Antes de considerar exitoso un video, la CLI debe comprobar al menos:

- el proceso FFmpeg terminó con código `0`;
- el MP4 de salida existe y no está vacío;
- existe un stream de video y, si la fuente tenía audio, al menos uno de audio;
- están presentes las pistas de subtítulos esperadas con idioma y título;
- ninguna pista de subtítulos está marcada como default;
- la pista inglesa de audio está marcada como default cuando fue identificada;
- la duración es consistente con la fuente dentro de una tolerancia definida.

La salida se escribe primero en staging y solo se publica en `output/` después
de superar la validación.

## Original y limpieza

El usuario no necesita conservar el original una vez comprobado el resultado,
pero eliminar videos es una operación destructiva. La política confirmada es:

- el comportamiento predeterminado conserva el original;
- nunca se elimina un original si el empaquetado o la verificación fallan;
- cualquier limpieza ocurre después de publicar el resultado válido;
- en modo interactivo se pregunta `¿Eliminar el archivo original? [s/N]`
  únicamente después de una verificación exitosa;
- responder Enter o `N` conserva el original;
- para automatización puede utilizarse `--delete-source` de forma explícita;
- `--delete-source` nunca está activo implícitamente y tampoco evita la
  verificación previa;
- si la eliminación falla, el MP4 final permanece válido y el comando informa
  el problema con un código de salida no exitoso o un estado parcial claramente
  distinguible.

## Red y privacidad

- Whisper transcribe localmente y utiliza CPU/GPU del equipo.
- La traducción predeterminada puede utilizar Google mediante
  `deep-translator` y, por tanto, requiere Internet y envía el texto a un
  servicio externo.
- El proyecto no se limita a traducción offline: resolver bien el problema y
  mantener calidad de traducción tiene prioridad.
- La CLI debe informar qué backend usará antes de enviar texto.

## Decisiones pendientes

1. Cuando existe un solo idioma, ¿se empaqueta únicamente el subtítulo
   disponible o la CLI debe intentar completar siempre inglés y español?
   Si debe completarlos: con solo inglés se puede traducir a español; con solo
   español falta decidir entre Whisper sobre el audio o traducción inversa.
2. Si el video ya contiene una pista embebida válida, ¿debe extraerse además a
   `sub_en/` o `sub_es/` para cumplir el contrato de conservar ambos SRT?
