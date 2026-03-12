#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

echo "=== Verifying installation ==="
python -c "
import sys
print('Python:', sys.version)

import tflite_runtime.interpreter as tflite
print('tflite-runtime: OK')

interp = tflite.Interpreter(model_path='models/best.tflite')
interp.allocate_tensors()
print('YOLO model: OK')

interp2 = tflite.Interpreter(model_path='models/camera_classifier.tflite')
interp2.allocate_tensors()
print('MobileNet model: OK')

import xgboost as xgb
model = xgb.Booster()
model.load_model('models/xgboost_model.json')
print('XGBoost model: OK')

print('=== All models verified ===')
"
