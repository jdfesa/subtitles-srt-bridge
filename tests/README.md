# Red de seguridad P0.1

Esta suite caracteriza comportamiento útil del prototipo y registra defectos
conocidos antes de refactorizarlo. Es determinista, offline y no necesita
dependencias de desarrollo externas.

## Comando único

```bash
python3 -m unittest discover -s tests -v
```

## Límites

- Whisper se reemplaza con un doble y solo se inspecciona su comando.
- FFprobe se reemplaza con respuestas JSON controladas.
- FFmpeg no se ejecuta; se caracteriza la construcción del comando importado.
- La traducción usa un traductor falso y nunca accede a Internet.
- Los movimientos y archivos se limitan a directorios temporales.
- No se modifican archivos de producción ni medios reales.
- Los modelos, rutas y puertos del núcleo nuevo se prueban sin adaptadores
  externos.
- Discovery, FFprobe y validación SRT se prueban con JSON controlado, sidecars
  temporales y asociaciones ambiguas sin modificar medios reales.
- El planner y su resumen se prueban con inventarios inmutables, elecciones de
  audio, salidas verificadas simuladas y colisiones en directorios temporales;
  no ejecutan ninguna etapa productiva.
- La transcripción usa extractores y reconocedores falsos. Se verifican el
  comando FFmpeg, cache/checksum del modelo, `task=transcribe`, selección de
  audio, staging, reanudación, validación y limpieza sin cargar Whisper real ni
  usar red.
- El remux usa runners y muxers falsos. Se comprueban mapeo total, copia de
  streams, SRT externos/generados, codificaciones, metadata, disposiciones,
  colisiones y limpieza de salidas parciales sin ejecutar FFmpeg real.
- La verificación y publicación usan inspecciones, verificadores, snapshots y
  reemplazos falsos. Se prueban streams, codecs, metadata, capítulos, duración,
  disposiciones, cambios posteriores, colisiones y movimientos atómicos sin
  FFprobe ni filesystem productivo.
- El archivado usa pruebas publicadas, recibos inmutables y movers inyectables.
  Se comprueban insumos exactos, sidecars generados, colisiones, orden de
  movimientos, rollback, fallos parciales y reanudación sin repetir etapas
  costosas.
- La orquestación usa cinco etapas falsas y artefactos tipados. Se comprueban
  ejecución, omisiones, bloqueo previo, aislamiento de fallos por video,
  reanudación, resultados parciales, resúmenes y códigos de salida sin invocar
  herramientas multimedia.
- El límite del prototipo legado se ejecuta con entradas temporales para
  comprobar que Python y `menu.sh` no anuncien éxito ante un proceso fallido.

## Defectos reproducidos

Los casos usan `unittest.expectedFailure`. Esto permite que la suite sea verde
sin presentar esos defectos como comportamiento correcto:

1. Whisper no se encuentra junto al Python activo de `.venv`.
2. Whisper escribe junto al video en lugar de utilizar staging.
3. El scanner legado ignora entradas MKV.
4. Sidecars vacíos se consideran trabajo terminado.
5. El parser de traducción no admite texto multilínea.
6. El último bloque con un salto final queda sin traducir.
7. Los separadores entre bloques se duplican y el último bloque puede omitirse.
8. El contenido CRLF no se procesa directamente.
9. `--sleep` se analiza pero no se pasa a la traducción.
10. Dos mensajes imprimen `{e}` y `{out_dir}` literalmente.
11. Un lote con traducciones fallidas devuelve estado `0`.

P0.9 corrigió la propagación del directorio inexistente o vacío y convirtió su
reproducción en una prueba de regresión normal. Quedan 11 defectos legados
marcados como `expectedFailure`.

Cuando una fase corrija o elimine el comportamiento afectado, debe quitarse
`expectedFailure`, ajustar el caso al nuevo módulo y mantener la intención como
prueba de regresión.
