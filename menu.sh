#!/bin/bash

# Configuration
VENV_DIR="./.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"

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
            read -p "Presiona Enter para volver al menú..."
            return
        fi
    fi
    ./setup.sh
    read -p "Presiona Enter para continuar..."
}

run_process() {
    if [ ! -f "$VENV_PYTHON" ]; then
        echo -e "${RED}❌ Error: No se encontró el entorno virtual.${NC}"
        echo "Por favor, ejecuta la opción '1. Instalar / Configurar' primero."
        read -p "Presiona Enter para volver al menú..."
        return
    fi

    echo -e "${GREEN}Introduce la ruta del directorio de videos (o presiona Enter para usar el actual):${NC}"
    # Use -r to read escapes literally; Python will handle cleanup
    read -r target_dir

    if [ -z "$target_dir" ]; then
        target_dir="."
    fi

    echo "Iniciando proceso en: $target_dir"
    if "$VENV_PYTHON" process_videos.py "$target_dir"; then
        echo -e "\n${GREEN}✅ Proceso finalizado correctamente.${NC}"
    else
        process_status=$?
        echo -e "\n${RED}❌ Proceso no completado (código $process_status).${NC}"
    fi
    read -p "Presiona Enter para volver al menú..."
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
        find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
        find . -name "*.pyc" -delete
        
        echo -e "${GREEN}✅ Entorno y archivos temporales eliminados.${NC}"
        echo "Ahora puedes usar la opción 1 para instalarlo nuevamente."
    else
        echo "Operación cancelada."
    fi
    read -p "Presiona Enter para volver al menú..."
}

show_help() {
    echo -e "${YELLOW}ℹ️  GUÍA DE USO${NC}"
    echo "---------------------------------------------------------"
    echo "1. Instalar: Ejecuta esto la primera vez para bajar las herramientas."
    echo "2. Procesar: Escanea los videos de la carpeta que elijas."
    echo "   - Genera subtítulos en inglés (si no existen)."
    echo "   - Los traduce automáticamente al español."
    echo "   - Organiza los archivos."
    echo "3. Limpiar: Borra el entorno virtual por si hubo errores."
    echo ""
    echo "Simplemente sigue las instrucciones en pantalla."
    echo "---------------------------------------------------------"
    read -p "Presiona Enter para volver al menú..."
}

# Main Loop
while true; do
    show_menu
    read -p "Selecciona una opción (1-5): " choice
    case $choice in
        1) run_setup ;;
        2) run_process ;;
        3) run_clean ;;
        4) show_help ;;
        5) echo "Adiós! 👋"; exit 0 ;;
        *) echo -e "${RED}Opción inválida.${NC}"; sleep 1 ;;
    esac
done
