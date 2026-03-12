import os
import warnings

# Suppress TF deprecation warnings
warnings.filterwarnings("ignore", category=UserWarning, module="tensorflow")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"           # suppress TF C++ INFO/WARNING
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"           # silence oneDNN notice

YOLO_MODEL_PATH = os.path.join("models", "best.tflite")
MOBILENET_MODEL_PATH = os.path.join("models", "camera_classifier.tflite")
XGB_MODEL_PATH = os.path.join("models", "xgboost_model.json")

# ── Verify files exist ──────────────────────────────────────────────
for label, path in [("YOLO", YOLO_MODEL_PATH),
                    ("MobileNet", MOBILENET_MODEL_PATH),
                    ("XGBoost", XGB_MODEL_PATH)]:
    if not os.path.exists(path):
        print(f"ERROR: {label} model not found at {path}")
        exit(1)
    print(f"{label} exists: True  ({os.path.getsize(path):,} bytes)")

# ── Load TFLite interpreter ─────────────────────────────────────────
try:
    # Prefer the new LiteRT package (future-proof)
    from ai_edge_litert import interpreter as litert  # type: ignore[import]
    Interpreter = litert.Interpreter
except ImportError:
    try:
        import tflite_runtime.interpreter as tflite_interp  # type: ignore[import]
        Interpreter = tflite_interp.Interpreter
    except ImportError:
        import tensorflow as tf  # type: ignore[import]
        Interpreter = tf.lite.Interpreter

# ── YOLO model ──────────────────────────────────────────────────────
interp = Interpreter(model_path=YOLO_MODEL_PATH)
interp.allocate_tensors()
inp = interp.get_input_details()
out = interp.get_output_details()
print(f"YOLO input:  {inp[0]['shape']}  {inp[0]['dtype']}")
print(f"YOLO output: {out[0]['shape']}  {out[0]['dtype']}")

# ── MobileNet model ─────────────────────────────────────────────────
interp2 = Interpreter(model_path=MOBILENET_MODEL_PATH)
interp2.allocate_tensors()
inp2 = interp2.get_input_details()
out2 = interp2.get_output_details()
print(f"MobileNet input:  {inp2[0]['shape']}  {inp2[0]['dtype']}")
print(f"MobileNet output: {out2[0]['shape']}  {out2[0]['dtype']}")

print("\n[OK] All models loaded successfully!")
