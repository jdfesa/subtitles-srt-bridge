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

## Defectos reproducidos

Los casos usan `unittest.expectedFailure`. Esto permite que la suite sea verde
sin presentar esos defectos como comportamiento correcto:

1. Whisper no se encuentra junto al Python activo de `.venv`.
2. Whisper escribe junto al video en lugar de utilizar staging.
3. El scanner legado ignora entradas MKV.
4. Sidecars vacíos se consideran trabajo terminado.
5. Un directorio inexistente no produce estado no exitoso.
6. El parser de traducción no admite texto multilínea.
7. El último bloque con un salto final queda sin traducir.
8. Los separadores entre bloques se duplican y el último bloque puede omitirse.
9. El contenido CRLF no se procesa directamente.
10. `--sleep` se analiza pero no se pasa a la traducción.
11. Dos mensajes imprimen `{e}` y `{out_dir}` literalmente.
12. Un lote con traducciones fallidas devuelve estado `0`.

Cuando una fase corrija o elimine el comportamiento afectado, debe quitarse
`expectedFailure`, ajustar el caso al nuevo módulo y mantener la intención como
prueba de regresión.
