# Subtitles Bridge Automation

Herramienta automatizada para generar, traducir y organizar subtítulos de videos localmente.
Utiliza **OpenAI Whisper** para la transcripción y **Deep Translator** (Google Backend) para la traducción, eliminando la necesidad de herramientas web manuales.

## 🚀 Características
*   **Generación Automática**: Crea subtítulos en inglés (`.srt`) a partir de archivos de video (`.mp4`) usando Whisper.
*   **Traducción Local**: Traduce automáticamente los subtítulos al español preservando los tiempos exactos.
*   **Organización Inteligente**:
    *   Subtítulos en **Español** (`.srt`) -> Se guardan junto al video (para reproducción directa).
    *   Subtítulos en **Inglés** (`.en.srt`) -> Se mueven ordenadamente a una subcarpeta `sub_en/`.
*   **Resume Inteligente**: Si se interrumpe el proceso, detecta los subtítulos ya generados y continúa desde donde se quedó.
*   **Estimación de Tiempo**: Muestra una barra de progreso y tiempo estimado (ETA) para grandes lotes de videos.

---

## 📋 Requisitos Previos

### Sistema Operativo
*   **Probado y optimizado para macOS** (Sonoma/Sequioa con Python 3.12).
*   *Debería funcionar en Linux/Windows*, pero el script de instalación automática (`setup.sh`) contiene optimizaciones específicas para Mac (Homebrew/LLVM).

### Dependencias del Sistema
Debes tener instalado:
1.  **Python 3.10+** (Recomendado 3.12).
2.  **FFmpeg**: Necesario para que Whisper procese el audio.
    *   macOS: `brew install ffmpeg`

---

## �️ Instalación y Uso

Este proyecto incluye un **Menú Interactivo** (`menu.sh`) que maneja todo el ciclo de vida del programa.

### 1. Iniciar el Menú
Abre tu terminal en la carpeta del proyecto y ejecuta:

```bash
./menu.sh
```

### 2. Opciones del Menú

*   **1. 🛠️ Instalar / Configurar (Setup)**:
    *   Crea un entorno virtual local (`.venv`).
    *   Instala las dependencias de Python (`openai-whisper`, `deep-translator`, etc.).
    *   **Nota para macOS**: Detecta e instala automáticamente `llvm@15` y `cmake` si faltan, necesarios para compilar librerías críticas (`llvmlite`).

*   **2. 🚀 Procesar Videos**:
    *   Te pedirá la ruta de la carpeta con tus videos.
    *   **Tip**: Puedes arrastrar la carpeta desde el Finder a la terminal. El script limpiará automáticamente los caracteres extraños.
    *   Comenzará a trabajar video por video mostrando el progreso.

*   **3. 🧹 Limpiar Entorno**:
    *   Utilidad de mantenimiento. Borra el entorno virtual y los archivos temporales (`__pycache__`). Útil si encuentras errores extraños o quieres reinstalar desde cero.

---

## 🐛 Solución de Problemas Comunes

### Error: `Failed building wheel for llvmlite`
Este fue el desafío principal durante el desarrollo en macOS con Python 3.12.
*   **Causa**: `llvmlite` necesita una versión específica de LLVM para compilarse, y las versiones más nuevas de Python entran en conflicto con las librerías del sistema por defecto.
*   **Solución**: El script `setup.sh` ahora maneja esto automáticamente instalando `llvm@15` via Homebrew y configurando las variables de entorno `LLVM_CONFIG` y `CMAKE_PREFIX_PATH` antes de instalar Python. **No deberías necesitar hacer nada manual.**

### Error: `Directory does not exist` al arrastrar carpetas
*   **Causa**: Al arrastrar carpetas al terminal en macOS, se agregan barras invertidas (`\`) para escapar espacios.
*   **Solución**: El script ahora incluye una función de "Sanitización" que limpia estas rutas automáticamente. Puedes arrastrar y soltar sin miedo.

---

## 📂 Estructura del Proyecto

*   `menu.sh`: Interfaz principal para el usuario.
*   `setup.sh`: Script de "backend" para la instalación y gestión de dependencias complejas.
*   `process_videos.py`: El cerebro de la operación. Contiene la lógica de Whisper, traducción y gestión de archivos.
*   `local_translate_srt.py`: Módulo auxiliar para la traducción de bloques de texto SRT.
*   `requirements.txt`: Lista de versiones exactas de librerías probadas (`llvmlite==0.43.0`, `numba==0.60.0`).

---

**Desarrollado para automatizar flujos de trabajo de traducción de video personal.**