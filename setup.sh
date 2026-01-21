#!/bin/bash

# Configuration
VENV_DIR="./.venv"

echo "🔹 Setting up environment for Subtitles Bridge..."

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install it first."
    exit 1
fi

# 2. Create Virtual Environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "✅ Virtual environment already exists at $VENV_DIR"
fi

# 3. Activate and Install Dependencies
echo "🔄 Activating environment and installing/updating dependencies..."
source "$VENV_DIR/bin/activate"

# Upgrade pip just in case
pip install --upgrade pip

# MacOS Specific Hack: Check for LLVM if installing llvmlite fails or needs building
if [[ "$(uname)" == "Darwin" ]]; then
    echo "🍎 macOS detected: Checking build dependencies..."

    # Ensure libomp is installed (needed for numba/pytorch)
    if ! brew list libomp &>/dev/null; then
        echo "   -> Installing libomp..."
        brew install libomp
    fi

    # Ensure cmake is installed (needed for building llvmlite)
    if ! command -v cmake &> /dev/null; then
        echo "   -> Installing cmake..."
        brew install cmake
    fi
    
    # Ensure llvm@15 is installed (needed for llvmlite >= 0.40)
    if ! brew list llvm@15 &>/dev/null; then
        echo "   -> Installing llvm@15..."
        brew install llvm@15
    fi

    # Set Environment Variables for the build
    LLVM_PREFIX=$(brew --prefix llvm@15)
    
    echo "   -> Configuring build environment using LLVM at $LLVM_PREFIX"
    export LLVM_CONFIG="$LLVM_PREFIX/bin/llvm-config"
    export CMAKE_PREFIX_PATH="$LLVM_PREFIX"
    # Some builds might need these too
    export LDFLAGS="-L$LLVM_PREFIX/lib"
    export CPPFLAGS="-I$LLVM_PREFIX/include"
fi

# Install requirements
echo "📦 Installing Python packages..."
if pip install -r requirements.txt; then
    echo "✅ Dependencies installed successfully!"
else
    echo "❌ Error installing dependencies."
    echo "   If the error is related to 'llvmlite' or 'numba', try running 'brew install llvm@15' manually."
    exit 1
fi

echo "🎉 Setup complete!"
echo "To use the tool, run:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 process_videos.py"
