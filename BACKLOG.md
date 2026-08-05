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

`setup.sh` instala `.venv/bin/whisper`, pero `menú.sh` ejecuta directamente
`.venv/bin/python3` sin activar el entorno. `shutil.which("whisper")` no encuentra
ese binario y el fallback apunta a un entorno diferente en `~/venvs/whisper`.

**Criterios de aceptación**

- Una instalación nueva realizada desde el menú puede procesar un video sin
  instalar Whisper globalmente.
- El ejecutable se resuelve desde el mismo entorno que `sys.executable` o se
  invoca como modulo Python.
- Si Whisper no existe, el error indica como reparar la instalación.

### [ ] P0.2 Sustituir o corregir el parser SRT

El regex actual deja sin traducir el último bloque cuando el archivo termina
con un único salto de línea y duplica líneas en blanco entre bloques.

**Criterios de aceptación**

- Se traducen todos los bloques con o sin salto de línea final.
- Se preservan índices, tiempos, texto multilinea y separadores válidos.
- Hay casos automatizados para LF, CRLF, archivo sin salto final, etiquetas y
  texto multilinea.
- Los bloques invalidos producen un error comprensible o se conservan mediante
  una política documentada; nunca se omiten silenciosamente.

### [ ] P0.3 Agregar pruebas de regresión del núcleo

Crear una suite pequeña y sin acceso a red. El traductor y la ejecución de
Whisper deben reemplazarse por dobles durante las pruebas.

**Criterios de aceptación**

- Cubre parseo/traducción SRT, nombres de salida, reanudación, `--force` y
  propagacion de fallos.
- Reproduce P0.1 y P0.2 antes de sus correcciones.
- Existe un comando único y documentado para ejecutar la suite.

### [ ] P0.4 Propagar fallos y corregir mensajes

`local_translate_srt.py` imprime `{e}` y `{out_dir}` literalmente en dos
mensajes. Ademas, ambos flujos pueden terminar con código `0` aunque una etapa
haya fallado, y el menú anuncia que el proceso finalizo sin distinguir exito de
error.

**Criterios de aceptación**

- Los mensajes muestran la excepción y ruta reales.
- El resumen distingue procesados, omitidos y fallidos.
- Cualquier fallo no recuperado produce un código de salida distinto de cero.
- El menú no comunica exito cuando el comando fallo.

### [ ] P0.5 Definir una política segura para archivos existentes

La existencia del archivo se usa como unica prueba de que una etapa termino.
Ademas, `video.srt` es tanto el nombre temporal esperado de Whisper como el
destino final en español, lo que puede reemplazar contenido previo.

**Criterios de aceptación**

- Whisper escribe en un directorio temporal o de staging separado.
- No se sobrescribe un SRT previo del usuario sin `--force` y una semántica
  documentada.
- Las escrituras finales son atómicas.
- Antes de omitir una etapa se valida al menos que el SRT sea legible y tenga
  bloques válidos.

### [ ] P0.6 Corregir la promesa de privacidad y conectividad

Whisper se ejecuta localmente, pero el backend predeterminado de traducción
Google requiere Internet y envía el texto del subtitulo a un servicio externo.

**Criterios de aceptación**

- README y ayuda distinguen transcripción local de traducción remota.
- Se documentan red, privacidad, posibles límites y credenciales por backend.
- Se decide si una traducción completamente offline es requisito o no.

## P1 - Hacer la CLI mantenible

### [ ] P1.1 Hacer los scripts independientes del directorio actual

Resolver la raíz desde la ubicación de cada script. Hoy `./.venv`, `./setup.sh`
y `process_videos.py` dependen de ejecutar `menú.sh` desde la raíz del repo.

### [ ] P1.2 Unificar configuración y semántica de la CLI

- Definir si `--force` regenera todo o aceptar flags por etapa.
- Exponer, si forman parte del alcance, modelo Whisper, idioma de origen,
  idioma destino, backend y pausa entre peticiones.
- Hacer que `--sleep` se aplique también desde `local_translate_srt.py`; hoy el
  argumento se analiza pero no se pasa a `translate_srt`.
- Mantener valores predeterminados simples para el caso común.

### [ ] P1.3 Separar orquestación, servicios y archivos

Extraer funciones pequenas para poder probar sin procesos reales ni red:

- descubrimiento de videos;
- resolución de rutas y estado por video;
- adaptador de Whisper;
- adaptadores de traducción;
- validación y escritura de SRT;
- resumen del lote y codigos de salida.

No hace falta introducir un framework ni una arquitectura de muchas capas.

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

- Definir una estrategia minima de lock o constraints.
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
- ETA basada solo en trabajos realmente procesados; los omitidos instantaneos
  hoy distorsionan el promedio.
- Mensajes consistentes y opción de salida menos verbosa para automatización.

## P2 - Evaluar solo con alcance confirmado

### [ ] P2.1 Optimizar traducción

Reutilizar el cliente de Google, agrupar texto respetando límites y aplicar
backoff con jitter. Medir primero; la implementación actual crea un traductor y
una peticion por línea.

### [ ] P2.2 Soportar mas entradas

Evaluar `.mov`, `.mkv`, selección recursiva y múltiples idiomas solo si aparecen
casos reales. Evitar ampliar la matriz antes de estabilizar MP4 inglés-español.

### [ ] P2.3 Aprovechar hardware disponible

Permitir seleccionar modelo/dispositivo y no fijar siempre `--fp16 False` si se
necesita rendimiento en equipos compatibles.

### [ ] P2.4 Empaquetar la herramienta

Considerar `pyproject.toml`, un entry point y releases solo cuando el uso fuera
del clon del repositorio lo justifique.

### [ ] P2.5 Completar metadatos del proyecto

Agregar licencia, política de contribución y changelog si el repositorio se va a
distribuir o aceptar contribuciones.

## Orden de ejecución recomendado

1. Acordar las decisiones de alcance de [`docs/PROJECT.md`](docs/PROJECT.md).
2. Implementar P0.3 junto con las reproducciones de P0.1 y P0.2.
3. Corregir P0.1, P0.2, P0.4 y P0.5 bajo pruebas.
4. Resolver P0.6 según la decision de privacidad.
5. Ejecutar P1 en incrementos pequeños.
6. Repriorizar P2 solo con evidencia de uso.

