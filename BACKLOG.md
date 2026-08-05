# Backlog

Backlog propuesto a partir de la revisión del repositorio del 2026-08-05.
Prioriza confiabilidad del flujo actual antes de ampliar funcionalidades.

## Convenciones

- **P0:** impide confiar en el flujo principal o contradice su promesa básica.
- **P1:** necesario para una primera versión mantenible y predecible.
- **P2:** mejora posterior; debe validarse contra una necesidad real.
- Los ítems no representan trabajo ya implementado.

## P0 - Corregir el flujo principal

### [ ] P0.1 Usar Whisper desde el entorno instalado

`setup.sh` instala `.venv/bin/whisper`, pero `menu.sh` ejecuta directamente
`.venv/bin/python3` sin activar el entorno. `shutil.which("whisper")` no encuentra
ese binario y el fallback apunta a un entorno diferente en `~/venvs/whisper`.

**Criterios de aceptación**

- Una instalación nueva realizada desde el menú puede procesar un video sin
  instalar Whisper globalmente.
- El ejecutable se resuelve desde el mismo entorno que `sys.executable` o se
  invoca como módulo Python.
- Si Whisper no existe, el error indica cómo reparar la instalación.

### [ ] P0.2 Sustituir o corregir el parser SRT

El regex actual deja sin traducir el último bloque cuando el archivo termina
con un único salto de línea y duplica líneas en blanco entre bloques.

**Criterios de aceptación**

- Se traducen todos los bloques con o sin salto de línea final.
- Se preservan índices, tiempos, texto multilínea y separadores válidos.
- Hay casos automatizados para LF, CRLF, archivo sin salto final, etiquetas y
  texto multilinea.
- Los bloques inválidos producen un error comprensible o se conservan mediante
  una política documentada; nunca se omiten silenciosamente.

### [ ] P0.3 Agregar pruebas de regresión del núcleo

Crear una suite pequeña y sin acceso a red. El traductor y la ejecución de
Whisper deben reemplazarse por dobles durante las pruebas.

**Criterios de aceptación**

- Cubre parseo/traducción SRT, asociación de archivos, matriz de planificación,
  nombres de salida, reanudación, `--force`, propagación de fallos y
  construcción del comando FFmpeg.
- Reproduce P0.1 y P0.2 antes de sus correcciones.
- Existe un comando único y documentado para ejecutar la suite.

### [ ] P0.4 Propagar fallos y corregir mensajes

`local_translate_srt.py` imprime `{e}` y `{out_dir}` literalmente en dos
mensajes. Además, ambos flujos pueden terminar con código `0` aunque una etapa
haya fallado, y el menú anuncia que el proceso finalizó sin distinguir éxito de
error.

**Criterios de aceptación**

- Los mensajes muestran la excepción y ruta reales.
- El resumen distingue procesados, omitidos y fallidos.
- Cualquier fallo no recuperado produce un código de salida distinto de cero.
- El menú no comunica éxito cuando el comando falló.

### [ ] P0.5 Definir una política segura para archivos existentes

La existencia del archivo se usa como única prueba de que una etapa terminó.
Además, `video.srt` es tanto el nombre temporal esperado de Whisper como el
destino final en español, lo que puede reemplazar contenido previo.

**Criterios de aceptación**

- Whisper escribe en un directorio temporal o de staging separado.
- No se sobrescribe un SRT previo del usuario sin `--force` y una semántica
  documentada.
- Las escrituras finales son atómicas.
- Antes de omitir una etapa se valida al menos que el SRT sea legible y tenga
  bloques válidos.
- El original se conserva por defecto.
- La limpieza solo ocurre después de verificar el MP4 final.
- El modo interactivo pregunta `¿Eliminar el archivo original? [s/N]`.
- La automatización requiere `--delete-source` explícito; nunca se activa de
  forma implícita.

### [ ] P0.6 Corregir la promesa de privacidad y conectividad

Whisper se ejecuta localmente, pero el backend predeterminado de traducción
Google requiere Internet y envía el texto del subtítulo a un servicio externo.

**Criterios de aceptación**

- README y ayuda distinguen transcripción local de traducción remota.
- Se documentan red, privacidad, posibles límites y credenciales por backend.
- Se decide si una traducción completamente offline es requisito o no.

### [ ] P0.7 Implementar preflight y plan condicional

Inspeccionar automáticamente cada video, sus streams, los SRT asociados y un
posible resultado previo. El plan debe omitir Whisper y traducción siempre que
los artefactos válidos ya existan.

**Criterios de aceptación**

- Detecta MP4/MKV del nivel principal, pistas embebidas y SRT en la raíz,
  `sub_en/` y `sub_es/`.
- Asocia por nombre de forma conservadora y pregunta cuando el idioma o la
  asociación sean ambiguos.
- Distingue `found`, `missing`, `invalid` y `ambiguous` por idioma.
- Muestra por video qué etapas ejecutará u omitirá antes de modificar archivos.
- Dos SRT existentes pasan directamente a empaquetado.
- Un solo idioma disponible aplica la política confirmada sin ejecutar etapas
  adicionales por accidente.
- Un resultado ya válido se omite.
- La lógica de planificación se prueba sin Whisper, red ni FFmpeg reales.

### [ ] P0.8 Integrar el MP4 final con pistas seleccionables

Conectar el pipeline por lotes con la capacidad importada en
`tools/normalize_video_mp4/`. Los SRT deben conservarse como archivos y también
incorporarse al MP4 como pistas opcionales, no quemadas en la imagen.

**Criterios de aceptación**

- Cada video exitoso produce un MP4 nuevo sin reemplazar el original.
- VLC muestra dos pistas identificadas como English (`eng`) y Spanish (`spa`).
- Los SRT en inglés y español permanecen disponibles en sus carpetas.
- Un MP4 compatible copia audio/video sin recomprimirlos.
- Para MKV se copian streams compatibles y solo se convierten los necesarios
  para producir un MP4 reproducible.
- El fallo de FFmpeg se refleja en el resumen y código de salida del lote.

## P1 - Hacer la CLI mantenible

### [ ] P1.1 Hacer los scripts independientes del directorio actual

Resolver la raíz desde la ubicación de cada script. Hoy `./.venv`, `./setup.sh`
y `process_videos.py` dependen de ejecutar `menu.sh` desde la raíz del repo.

### [ ] P1.2 Unificar configuración y semántica de la CLI

- Definir si `--force` regenera todo o aceptar flags por etapa.
- Exponer, si forman parte del alcance, modelo Whisper, idioma de origen,
  idioma destino, backend y pausa entre peticiones.
- Hacer que `--sleep` se aplique también desde `local_translate_srt.py`; hoy el
  argumento se analiza pero no se pasa a `translate_srt`.
- Mantener valores predeterminados simples para el caso común.

### [ ] P1.3 Separar orquestación, servicios y archivos

Extraer funciones pequeñas para poder probar sin procesos reales ni red:

- descubrimiento de videos;
- resolución de rutas y estado por video;
- adaptador de Whisper;
- adaptadores de traducción;
- validación y escritura de SRT;
- resumen del lote y códigos de salida.

No hace falta introducir un framework ni una arquitectura de muchas capas.

Antes de dividir `tools/normalize_video_mp4/normalize_video_mp4.py`, agregar
pruebas de caracterización para sus funciones puras y la construcción del
comando FFmpeg. Luego separar únicamente donde aporte claridad:

- inspección de medios con FFprobe;
- políticas de codecs y streams;
- detección y metadata de subtítulos;
- construcción y ejecución de FFmpeg;
- interfaz CLI.

### [ ] P1.4 Robustecer instalación y diagnóstico

- Verificar `ffmpeg`, Python compatible, Homebrew solo cuando sea necesario y
  espacio aproximado para entorno/modelo.
- No asumir que `brew` existe antes de invocarlo.
- Explicar que Whisper descarga el modelo en el primer uso.
- Ofrecer un comando `doctor` o chequeo previo equivalente.
- Revisar si LLVM 15 sigue siendo necesario para las versiones soportadas.

### [ ] P1.5 Definir dependencias reproducibles

`openai-whisper` y `deep-translator` no tienen versión fijada, aunque el README
habla de versiones exactas.

- Definir una estrategia mínima de lock o constraints.
- Separar dependencias opcionales de LibreTranslate y DeepL, o eliminar
  backends que no formen parte del producto.
- Documentar las versiones de Python realmente soportadas.

### [ ] P1.6 Agregar checks automáticos

- Formato/lint de Python y shell.
- Pruebas en cada cambio mediante CI, al menos en macOS si es la plataforma
  soportada.
- Smoke test de `--help` sin descargar modelos ni usar servicios externos.

### [ ] P1.7 Mejorar observabilidad sin complicar la UX

- Resumen final con éxitos, omitidos y fallos.
- ETA basada solo en trabajos realmente procesados; los omitidos instantáneos
  hoy distorsionan el promedio.
- Mensajes consistentes y opción de salida menos verbosa para automatización.

### [ ] P1.8 Preparar portabilidad sin frenar macOS

- Mantener el núcleo en Python y evitar rutas o comandos exclusivos de POSIX.
- Dejar `menu.sh` como wrapper de macOS/Linux, no como única interfaz.
- Diseñar instalación y detección de FFmpeg por plataforma.
- Tras estabilizar macOS, validar el contrato en Linux y Windows mediante CI y
  pruebas de instalación limpia.

## P2 - Evaluar solo con alcance confirmado

### [ ] P2.1 Optimizar traducción

Reutilizar el cliente de Google, agrupar texto respetando límites y aplicar
backoff con jitter. Medir primero; la implementación actual crea un traductor y
una petición por línea.

### [ ] P2.2 Soportar más entradas

Estabilizar primero `.mp4` y `.mkv`. Evaluar después `.mov`, otros contenedores,
selección recursiva y más idiomas solo cuando aparezcan casos reales.

### [ ] P2.3 Aprovechar hardware disponible

Permitir seleccionar modelo/dispositivo y no fijar siempre `--fp16 False` si se
necesita rendimiento en equipos compatibles.

### [ ] P2.4 Empaquetar la herramienta

Considerar `pyproject.toml`, un entry point y releases solo cuando el uso fuera
del clon del repositorio lo justifique.

### [ ] P2.5 Completar metadatos del proyecto

Agregar licencia, política de contribución y changelog si el repositorio se va a
distribuir o aceptar contribuciones.

### [ ] P2.6 Ofrecer un contenedor opcional

Después de fijar dependencias y tener CI, evaluar un Dockerfile como entorno de
referencia Linux/CPU. No convertirlo en requisito para usuarios de macOS ni en
sustituto de las pruebas nativas por sistema operativo y arquitectura.

## Orden de ejecución recomendado

1. Acordar las decisiones de alcance de [`docs/PROJECT.md`](docs/PROJECT.md).
2. Cerrar las decisiones de [`docs/WORKFLOW.md`](docs/WORKFLOW.md).
3. Implementar P0.3 junto con las reproducciones de P0.1 y P0.2.
4. Implementar el planner P0.7 bajo pruebas.
5. Corregir P0.1, P0.2, P0.4 y P0.5 bajo pruebas.
6. Integrar el empaquetado P0.8 y su verificación.
7. Completar la documentación de red P0.6.
8. Ejecutar P1 en incrementos pequeños.
9. Repriorizar P2 solo con evidencia de uso.
