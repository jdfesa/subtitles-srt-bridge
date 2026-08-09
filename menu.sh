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
    echo "=================================================="
    echo "  🎬  SUBTITLES BRIDGE"
    echo "  Subtítulos seleccionables en un MKV verificado"
    echo "=================================================="
    echo "1. 🛠️  Preparar / verificar instalación"
    echo "2. 🔎 Inspeccionar carpeta sin hacer cambios"
    echo "3. 🚀 Procesar carpeta"
    echo "4. ↩️  Reanudar archivado pendiente"
    echo "5. 🩺 Diagnosticar instalación"
    echo "6. ℹ️  Ayuda y flujo recomendado"
    echo "7. 🧹 Restablecer entorno local (avanzado)"
    echo "8. 🚪 Salir"
    echo "=================================================="
}

pause_menu() {
    read -r -p "Presiona Enter para volver al menú..."
}

require_runtime() {
    if [ -x "$VENV_PYTHON" ]; then
        return 0
    fi
    echo -e "${RED}❌ No se encontró el entorno virtual.${NC}"
    echo "Ejecuta primero '1. Preparar / verificar instalación'."
    return 1
}

prompt_target_dir() {
    echo -e "${GREEN}Ruta de la carpeta con videos (Enter = directorio actual):${NC}"
    echo "Puedes escribirla o arrastrarla desde Finder."
    # Drag-and-drop paths arrive with shell-escaped spaces; read must unescape them.
    # shellcheck disable=SC2162
    IFS= read TARGET_DIR
    if [ -z "$TARGET_DIR" ]; then
        TARGET_DIR="$PWD"
    fi
}

report_cli_status() {
    action=$1
    status=$2
    case $status in
        0)
            case $action in
                Inspección)
                    echo -e "${GREEN}✅ Inspección completada: no se modificó ningún archivo.${NC}"
                    ;;
                Procesamiento)
                    echo -e "${GREEN}✅ Procesamiento finalizado correctamente.${NC}"
                    ;;
                Reanudación)
                    echo -e "${GREEN}✅ Reanudación completada correctamente.${NC}"
                    ;;
                Diagnóstico)
                    echo -e "${GREEN}✅ Diagnóstico finalizado. Revisa cualquier advertencia mostrada.${NC}"
                    ;;
            esac
            ;;
        1)
            echo -e "${RED}❌ $action falló (código 1).${NC}"
            echo "Revisa la etapa, ruta o requisito informado arriba."
            ;;
        2)
            echo -e "${YELLOW}⚠️  El lote necesita una decisión (código 2).${NC}"
            echo "No se ejecutó ningún video. Revisa la inspección y, si corresponde,"
            echo "usa la CLI con --audio SOURCE=STREAM_INDEX."
            ;;
        3)
            echo -e "${YELLOW}⚠️  Resultado parcial (código 3): el MKV publicado se conserva.${NC}"
            echo "Corrige el problema de archivado y elige '4. Reanudar archivado pendiente'."
            ;;
        *)
            echo -e "${RED}❌ $action terminó con un código inesperado: $status.${NC}"
            ;;
    esac
}

run_setup() {
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}⚠️  Ya existe un entorno virtual en $VENV_DIR${NC}"
        echo "¿Deseas verificarlo y actualizar sus dependencias? (s/n)"
        read -r answer
        if [[ "$answer" != "s" && "$answer" != "S" ]]; then
            echo "Operación cancelada."
            pause_menu
            return
        fi
    fi
    if "$PROJECT_ROOT/setup.sh"; then
        echo -e "${GREEN}✅ Instalación y diagnóstico completados.${NC}"
    else
        setup_status=$?
        echo -e "${RED}❌ La instalación no se completó (código $setup_status).${NC}"
    fi
    pause_menu
}

run_workspace_action() {
    action=$1
    shift
    if ! require_runtime; then
        pause_menu
        return
    fi
    prompt_target_dir
    echo "$action en: $TARGET_DIR"
    "$VENV_PYTHON" "$CLI_SCRIPT" "$TARGET_DIR" "$@"
    status=$?
    echo ""
    report_cli_status "$action" "$status"
    pause_menu
}

run_doctor() {
    if ! require_runtime; then
        pause_menu
        return
    fi
    "$VENV_PYTHON" "$CLI_SCRIPT" --doctor
    status=$?
    echo ""
    report_cli_status "Diagnóstico" "$status"
    pause_menu
}

run_clean() {
    echo -e "${RED}⚠️  ACCIÓN AVANZADA${NC}"
    echo "Se eliminarán únicamente '$VENV_DIR' y caches Python del repositorio."
    echo "No se modificarán videos, output/ ni trash/."
    echo "¿Estás seguro de continuar? (s/n)"
    read -r answer
    if [[ "$answer" == "s" || "$answer" == "S" ]]; then
        echo "Eliminando entorno virtual..."
        rm -rf "$VENV_DIR"
        echo "Limpiando caches de Python..."
        find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
        find "$PROJECT_ROOT" -name "*.pyc" -delete
        echo -e "${GREEN}✅ Entorno local restablecido.${NC}"
        echo "Ahora puedes usar la opción 1 para prepararlo nuevamente."
    else
        echo "Operación cancelada."
    fi
    pause_menu
}

show_help() {
    echo -e "${YELLOW}ℹ️  OBJETIVO Y FLUJO RECOMENDADO${NC}"
    echo "---------------------------------------------------------"
    echo "OBJETIVO"
    echo "  Reunir cada video y todos sus subtítulos válidos en un"
    echo "  único MKV con pistas seleccionables y no predeterminadas."
    echo ""
    echo "FLUJO NORMAL"
    echo "  1. Prepara la instalación una vez."
    echo "  2. Coloca MP4/MKV y sus SRT asociados en una carpeta."
    echo "  3. Inspecciona la carpeta sin cambios."
    echo "  4. Procesa cuando el plan esté listo."
    echo "  5. Revisa el MKV en output/ y la cuarentena trash/."
    echo ""
    echo "REGLAS DE SEGURIDAD"
    echo "  - Reutiliza todos los subtítulos válidos encontrados."
    echo "  - Usa Whisper solo si no existe ningún subtítulo válido."
    echo "  - No comprime ni recodifica audio o video."
    echo "  - Verifica la salida antes de mover insumos."
    echo "  - trash/ es cuarentena reversible: nunca se vacía ni sobrescribe."
    echo ""
    echo "SI ALGO QUEDA PENDIENTE"
    echo "  - Código 2: revisa preflight; una selección de audio puede requerir"
    echo "    la CLI directa con --audio SOURCE=STREAM_INDEX."
    echo "  - Código 3: corrige el archivado y usa la opción Reanudar."
    echo "  - Doctor comprueba Python, FFmpeg, FFprobe y Whisper sin procesar videos."
    echo "---------------------------------------------------------"
    pause_menu
}

while true; do
    show_menu
    read -r -p "Selecciona una opción (1-8): " choice
    case $choice in
        1) run_setup ;;
        2) run_workspace_action "Inspección" --preflight ;;
        3) run_workspace_action "Procesamiento" ;;
        4) run_workspace_action "Reanudación" --resume ;;
        5) run_doctor ;;
        6) show_help ;;
        7) run_clean ;;
        8)
            echo "¡Hasta luego! 👋"
            exit 0
            ;;
        *)
            echo -e "${RED}Opción inválida.${NC}"
            sleep 1
            ;;
    esac
done
