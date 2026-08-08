#!/bin/bash

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
CLI_SCRIPT="$PROJECT_ROOT/subtitles_bridge_cli.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "🔹 Setting up environment for Subtitles Bridge..."

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "❌ Python 3 is not available: $PYTHON_BIN"
    echo "   Install Python 3.10 through 3.13 with the method appropriate for your platform."
    exit 1
fi

if ! PYTHON_VERSION=$("$PYTHON_BIN" -c 'import platform, sys; print(platform.python_version()); raise SystemExit(0 if (3, 10) <= sys.version_info < (3, 14) else 1)'); then
    echo "❌ Python $PYTHON_VERSION is unsupported. Python 3.10 through 3.13 is required."
    exit 1
fi
echo "✅ Python $PYTHON_VERSION: $PYTHON_BIN"

missing_media_tools=0
for media_tool in ffmpeg ffprobe; do
    media_path=$(command -v "$media_tool" 2>/dev/null || true)
    if [ -z "$media_path" ]; then
        echo "❌ $media_tool was not found on PATH."
        missing_media_tools=1
    elif ! "$media_path" -version >/dev/null 2>&1; then
        echo "❌ $media_tool exists but cannot execute successfully: $media_path"
        missing_media_tools=1
    else
        echo "✅ $media_tool: $media_path"
    fi
done

if [ "$missing_media_tools" -ne 0 ]; then
    echo "   Install the FFmpeg package with your platform's package manager."
    echo "   Both ffmpeg and ffprobe must then be available on PATH."
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment at $VENV_DIR..."
    if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
        echo "❌ Could not create the virtual environment."
        exit 1
    fi
else
    echo "✅ Virtual environment already exists at $VENV_DIR"
fi

if [ ! -x "$VENV_PYTHON" ]; then
    echo "❌ Virtual environment Python is unavailable: $VENV_PYTHON"
    exit 1
fi

if ! VENV_PYTHON_VERSION=$("$VENV_PYTHON" -c 'import platform, sys; print(platform.python_version()); raise SystemExit(0 if (3, 10) <= sys.version_info < (3, 14) else 1)'); then
    echo "❌ Virtual environment uses unsupported Python $VENV_PYTHON_VERSION; Python 3.10 through 3.13 is required."
    echo "   Recreate $VENV_DIR with a compatible interpreter."
    exit 1
fi
echo "✅ Virtual environment Python $VENV_PYTHON_VERSION"

echo "🔄 Updating pip in the virtual environment..."
if ! "$VENV_PYTHON" -m pip install --upgrade pip; then
    echo "❌ Could not update pip in $VENV_DIR"
    exit 1
fi

echo "📦 Installing Python packages..."
if ! "$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"; then
    echo "❌ Error installing Python dependencies."
    echo "   Review the pip error above; setup does not install system packages automatically."
    exit 1
fi

echo "🔎 Running the portable runtime doctor..."
if ! "$VENV_PYTHON" "$CLI_SCRIPT" --doctor; then
    echo "❌ Runtime diagnostics found a required dependency problem."
    exit 1
fi

echo "🎉 Setup complete!"
echo "The Whisper model is not downloaded automatically."
echo "When network access is acceptable, preload the default model explicitly with:"
echo "  \"$VENV_PYTHON\" -c \"import whisper; whisper.load_model('small')\""
echo "Then verify it again with:"
echo "  \"$VENV_PYTHON\" \"$CLI_SCRIPT\" --doctor"
echo "To process videos, run:"
echo "  \"$VENV_PYTHON\" \"$CLI_SCRIPT\" /ruta/a/videos"
