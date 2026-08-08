#!/bin/bash

# Configuration
PROJECT_ROOT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
CLI_SCRIPT="$PROJECT_ROOT/subtitles_bridge_cli.py"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

show_menu() {
    clear
    echo "========================================="
    echo "   🎬  SUBTITLES BRIDGE - MENU        "
    echo "========================================="
    echo "1. 🛠️  Instalar / Configurar (Setup)"
    echo "2. 🚀 Procesar Videos"
    echo "3. 🧹 Limpiar Entorno (Solución de errores)"
    echo "4. ℹ️  Cómo usar (Ayuda)"
    echo "5. 🚪 Salir"
    echo "========================================="
}

run_setup() {
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}⚠️  ADVERTENCIA: Ya se detectó un entorno virtual en $VENV_DIR${NC}"
        echo "¿Deseas reinstalar/actualizar las dependencias? (s/n)"
        read -r answer
        if [[ "$answer" != "s" && "$answer" != "S" ]]; then
            echo "Operación cancelada."
            read -r -p "Presiona Enter para volver al menú..."
            return
        fi
    fi
    if "$PROJECT_ROOT/setup.sh"; then
        echo -e "${GREEN}✅ Instalación y diagnóstico completados.${NC}"
    else
        setup_status=$?
        echo -e "${RED}❌ La instalación no se completó (código $setup_status).${NC}"
    fi
    read -r -p "Presiona Enter para continuar..."
}

run_process() {
    if [ ! -x "$VENV_PYTHON" ]; then
        echo -e "${RED}❌ Error: No se encontró el entorno virtual.${NC}"
        echo "Por favor, ejecuta la opción '1. Instalar / Configurar' primero."
        read -r -p "Presiona Enter para volver al menú..."
        return
    fi

    echo -e "${GREEN}Introduce la ruta del directorio de videos (o presiona Enter para usar el actual):${NC}"
    # Terminal drag-and-drop may escape spaces with backslashes.
    # Drag-and-drop paths arrive with shell-escaped spaces; read must unescape them.
    # shellcheck disable=SC2162
    IFS= read target_dir

    if [ -z "$target_dir" ]; then
        target_dir="$PWD"
    fi

    echo "Iniciando proceso en: $target_dir"
    if "$VENV_PYTHON" "$CLI_SCRIPT" "$target_dir"; then
        echo -e "\n${GREEN}✅ Proceso finalizado correctamente.${NC}"
    else
        process_status=$?
        echo -e "\n${RED}❌ Proceso no completado (código $process_status).${NC}"
    fi
    read -r -p "Presiona Enter para volver al menú..."
}

run_clean() {
    echo -e "${RED}⚠️  ATENCIÓN ⚠️${NC}"
    echo "Esta opción eliminará la carpeta '$VENV_DIR'."
    echo "Úsala si la instalación falló o si quieres empezar de cero."
    echo "¿Estás seguro de continuar? (s/n)"
    read -r answer
    if [[ "$answer" == "s" || "$answer" == "S" ]]; then
        echo "Eliminando entorno virtual..."
        rm -rf "$VENV_DIR"

        echo "Limpiando caches de Python..."
        find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
        find "$PROJECT_ROOT" -name "*.pyc" -delete

        echo -e "${GREEN}✅ Entorno y archivos temporales eliminados.${NC}"
        echo "Ahora puedes usar la opción 1 para instalarlo nuevamente."
    else
        echo "Operación cancelada."
    fi
    read -r -p "Presiona Enter para volver al menú..."
}

show_help() {
    echo -e "${YELLOW}ℹ️  GUÍA DE USO${NC}"
    echo "---------------------------------------------------------"
    echo "1. Instalar: Ejecuta esto la primera vez para bajar las herramientas."
    echo "2. Procesar: Ejecuta el pipeline seguro sobre la carpeta elegida."
    echo "   - Reutiliza todos los subtítulos válidos disponibles."
    echo "   - Genera uno con Whisper solo cuando no existe ninguno."
    echo "   - Crea y verifica un MKV sin recodificar los streams."
    echo "   - Mueve los insumos incorporados a trash/ al finalizar."
    echo "   - La CLI directa ofrece --preflight, --audio y --resume."
    echo "   - También admite --whisper-model y --whisper-device."
    echo "   - Usa --doctor para comprobar Python, FFmpeg, FFprobe y Whisper."
    echo "3. Limpiar: Borra el entorno virtual por si hubo errores."
    echo ""
    echo "Simplemente sigue las instrucciones en pantalla."
    echo "---------------------------------------------------------"
    read -r -p "Presiona Enter para volver al menú..."
}

# Main Loop
while true; do
    show_menu
    read -r -p "Selecciona una opción (1-5): " choice
    case $choice in
        1) run_setup ;;
        2) run_process ;;
        3) run_clean ;;
        4) show_help ;;
        5)
            echo "Adiós! 👋"
            exit 0
            ;;
        *)
            echo -e "${RED}Opción inválida.${NC}"
            sleep 1
            ;;
    esac
done
