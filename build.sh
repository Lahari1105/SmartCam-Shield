#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Try installing tflite-runtime with multiple fallback versions
echo "=== Installing TFLite runtime ==="
pip install tflite-runtime==2.14.0 2>/dev/null \
  || pip install tflite-runtime 2>/dev/null \
  || pip install ai-edge-litert 2>/dev/null \
  || { echo "WARNING: Could not install tflite-runtime, falling back to full tensorflow"; pip install tensorflow-cpu --no-cache-dir; }

echo "=== Build complete ==="
python -c "
import os, sys
print('Python:', sys.version)
# Check tflite availability
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
            sys.exit(1)

# Check model files
models_dir = os.path.join(os.path.dirname(os.path.abspath('.')), 'models')
if not os.path.isdir(models_dir):
    models_dir = 'models'
for f in ['best.tflite', 'camera_classifier.tflite', 'xgboost_model.json']:
    path = os.path.join(models_dir, f)
    if os.path.exists(path):
        print(f'  {f}: OK ({os.path.getsize(path):,} bytes)')
    else:
        print(f'  {f}: MISSING at {path}')
"
