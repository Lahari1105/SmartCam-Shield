#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Try installing tflite-runtime with multiple fallback versions
echo "=== Installing TFLite runtime ==="

TFLITE_INSTALLED=0

# Attempt 1: tflite-runtime pinned version
if pip install tflite-runtime==2.14.0 2>/dev/null; then
    echo "Installed tflite-runtime==2.14.0"
    TFLITE_INSTALLED=1
fi

# Attempt 2: tflite-runtime latest
if [ "$TFLITE_INSTALLED" -eq 0 ]; then
    if pip install tflite-runtime 2>/dev/null; then
        echo "Installed tflite-runtime (latest)"
        TFLITE_INSTALLED=1
    fi
fi

# Attempt 3: ai-edge-litert
if [ "$TFLITE_INSTALLED" -eq 0 ]; then
    if pip install ai-edge-litert 2>/dev/null; then
        echo "Installed ai-edge-litert"
        TFLITE_INSTALLED=1
    fi
fi

# Attempt 4: tensorflow-cpu (heavy but guaranteed to work)
if [ "$TFLITE_INSTALLED" -eq 0 ]; then
    echo "Falling back to tensorflow-cpu..."
    pip install tensorflow-cpu --no-cache-dir
    echo "Installed tensorflow-cpu"
    TFLITE_INSTALLED=1
fi

echo "=== Build complete ==="
python -c "
import sys
print('Python:', sys.version)
try:
    import tflite_runtime.interpreter as tflite
    print('TFLite runtime: OK (tflite-runtime)')
except ImportError:
    try:
        from ai_edge_litert import interpreter
        print('TFLite runtime: OK (ai-edge-litert)')
    except ImportError:
        try:
            import tensorflow as tf
            print('TFLite runtime: OK (tensorflow)', tf.__version__)
        except ImportError:
            print('ERROR: No TFLite runtime available!')
"
