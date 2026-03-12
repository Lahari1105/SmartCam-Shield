from __future__ import annotations

from flask import Flask, render_template, request, jsonify, session, redirect, url_for  # pyre-ignore[21]
from flask_cors import CORS  # pyre-ignore[21]
from functools import wraps
import os
import io
import base64
import uuid
import traceback
from datetime import datetime, timezone
import numpy as np  # pyre-ignore[21]
from PIL import Image  # pyre-ignore[21]
import cv2  # pyre-ignore[21]

# TensorFlow Lite — cascading fallback for Render/Linux compatibility
tflite = None
try:
    import tflite_runtime.interpreter as tflite  # pyre-ignore[21]  # type: ignore[import]
    print("[STARTUP] Using tflite-runtime")
except Exception:
    try:
        from ai_edge_litert import interpreter as tflite  # pyre-ignore[21]  # type: ignore[import]
        print("[STARTUP] Using ai-edge-litert")
    except Exception:
        try:
            import tensorflow as tf  # pyre-ignore[21]  # type: ignore[import]
            tflite = tf.lite  # type: ignore
            print(f"[STARTUP] Using full tensorflow {tf.__version__}")
        except Exception as e:
            print(f"[STARTUP] WARNING: No TFLite runtime available! Error: {e}")
            print("[STARTUP] Models will NOT be loaded — install tflite-runtime or tensorflow")
            tflite = None

# XGBoost
import xgboost as xgb  # pyre-ignore[21]

# MongoDB
from pymongo import MongoClient  # pyre-ignore[21]
from bson.objectid import ObjectId  # pyre-ignore[21]

# Password hashing
import bcrypt  # pyre-ignore[21]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())
CORS(app)

# --------------------------------------------------
# MONGODB CONNECTION (lazy — app starts even if Mongo is down)
# --------------------------------------------------

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://lmekala_db_user:Lahari1516@cluster0.udmpuon.mongodb.net/smartcam_shield?appName=Cluster0")
print(f"[DEBUG] MONGO_URI = {MONGO_URI}")
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo_client["smartcam_shield"]
users_collection = db["users"]
scans_collection = db["scan_history"]

_indexes_created = False

def ensure_indexes():
    global _indexes_created
    if _indexes_created:
        return
    try:
        users_collection.create_index("username", unique=True)
        users_collection.create_index("email", unique=True)
        _indexes_created = True
    except Exception:
        pass  # will retry next call

@app.before_request
def _ensure_mongo_indexes():
    ensure_indexes()

# --------------------------------------------------
# UPLOAD CONFIG
# --------------------------------------------------
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max

# --------------------------------------------------
# PATHS
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

YOLO_MODEL_PATH = os.path.join(BASE_DIR, "models", "best.tflite")
MOBILENET_MODEL_PATH = os.path.join(BASE_DIR, "models", "camera_classifier.tflite")
XGB_MODEL_PATH = os.path.join(BASE_DIR, "models", "xgboost_model.json")

# --------------------------------------------------
# LABELS
# --------------------------------------------------
MOBILENET_LABELS = ["normal_object", "hidden_camera"]
YOLO_LABELS = ["hidden_camera"]

# Thresholds (lowered for better sensitivity with these models)
MOBILENET_THRESHOLD = 0.40
YOLO_CONF_THRESHOLD = 0.15

# --------------------------------------------------
# LOAD TFLITE MODELS
# --------------------------------------------------
def load_tflite_model(model_path):
    if tflite is None:
        print(f"Cannot load model (no TFLite runtime): {model_path}")
        return None
    if not os.path.exists(model_path):
        print(f"Model file not found: {model_path}")
        return None
    try:
        interpreter = tflite.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        print(f"Model loaded successfully: {model_path}")
        return interpreter
    except Exception as e:
        print(f"Failed to load model {model_path}: {e}")
        return None

yolo_interpreter = load_tflite_model(YOLO_MODEL_PATH)
mobilenet_interpreter = load_tflite_model(MOBILENET_MODEL_PATH)

# --------------------------------------------------
# LOAD XGBOOST MODEL
# --------------------------------------------------
xgb_model = None
if os.path.exists(XGB_MODEL_PATH):
    try:
        xgb_model = xgb.Booster()
        xgb_model.load_model(XGB_MODEL_PATH)
        print(f"XGBoost model loaded successfully: {XGB_MODEL_PATH}")
    except Exception as e:
        print(f"Failed to load XGBoost model: {e}")
        xgb_model = None
else:
    print(f"XGBoost model not found: {XGB_MODEL_PATH}")

# --------------------------------------------------
# AUTH DECORATOR
# --------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Authentication required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# --------------------------------------------------
# HELPER: BASE64 IMAGE TO PIL
# --------------------------------------------------
def decode_base64_image(image_data):
    if "," in image_data:
        header, encoded = image_data.split(",", 1)
    else:
        encoded = image_data
    image_bytes = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return image

# --------------------------------------------------
# HELPER: PREPROCESS IMAGE
# --------------------------------------------------
def preprocess_image(image, size, normalize=True):
    image = image.resize(size)
    img = np.array(image).astype(np.float32)
    if len(img.shape) == 2:
        img = np.stack([img] * 3, axis=-1)
    if normalize:
        img = img / 255.0
    img = np.expand_dims(img, axis=0)
    return img

# --------------------------------------------------
# HELPER: RUN TFLITE
# --------------------------------------------------
def run_tflite(interpreter, input_data):
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    input_index = input_details[0]["index"]
    input_dtype = input_details[0]["dtype"]

    if input_dtype == np.uint8:
        input_scale, input_zero_point = input_details[0]["quantization"]
        if input_scale > 0:
            input_data = input_data / input_scale + input_zero_point
            input_data = input_data.astype(np.uint8)
        else:
            input_data = input_data.astype(np.uint8)
    else:
        input_data = input_data.astype(input_dtype)

    interpreter.set_tensor(input_index, input_data)
    interpreter.invoke()

    outputs = []
    for out in output_details:
        outputs.append(interpreter.get_tensor(out["index"]))

    return outputs, input_details, output_details

# --------------------------------------------------
# MOBILENET LOGIC
# --------------------------------------------------
def predict_mobilenet(image):
    if mobilenet_interpreter is None:
        return {
            "available": False,
            "label": "model_not_loaded",
            "confidence": 0.0
        }

    input_tensor = preprocess_image(image, (224, 224), normalize=True)
    outputs, _, _ = run_tflite(mobilenet_interpreter, input_tensor)
    preds = outputs[0]
    preds = np.array(preds).squeeze()

    if preds.ndim == 0:
        preds = np.array([float(preds)])

    if len(preds.shape) == 0:
        preds = np.array([preds])

    if preds.size == 1:
        hidden_camera_prob = float(preds[0])
        normal_prob = 1.0 - hidden_camera_prob
        probs = np.array([normal_prob, hidden_camera_prob])
    else:
        probs = preds.astype(float)
        exp_scores = np.exp(probs - np.max(probs))
        probs = exp_scores / np.sum(exp_scores)

    pred_idx = int(np.argmax(probs))
    pred_conf = float(probs[pred_idx])
    label = MOBILENET_LABELS[pred_idx] if pred_idx < len(MOBILENET_LABELS) else f"class_{pred_idx}"
    suspicious = (label == "hidden_camera" and pred_conf >= MOBILENET_THRESHOLD)

    return {
        "available": True,
        "label": label,
        "confidence": round(float(pred_conf), 4),  # pyre-ignore[6]
        "suspicious": suspicious,
        "raw_probs": probs.tolist()
    }

# --------------------------------------------------
# YOLO LOGIC
# --------------------------------------------------
def decode_yolo_output(raw_output):
    arr = np.array(raw_output)
    arr = np.squeeze(arr)
    detections = []

    print(f"[YOLO DEBUG] Raw output shape: {arr.shape}, ndim: {arr.ndim}")

    if arr.ndim == 1:
        # Single detection or flat output — try interpreting as [x, y, w, h, conf, class...]
        if len(arr) >= 6:
            x, y, w, h = arr[:4]
            class_scores = arr[4:]
            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])
            if confidence >= YOLO_CONF_THRESHOLD:
                label = YOLO_LABELS[class_id] if class_id < len(YOLO_LABELS) else f"class_{class_id}"
                x1 = float(x - w / 2)
                y1 = float(y - h / 2)
                x2 = float(x + w / 2)
                y2 = float(y + h / 2)
                detections.append({
                    "label": label,
                    "confidence": round(float(confidence), 4),  # pyre-ignore[6]
                    "bbox": [x1, y1, x2, y2],
                    "bbox_center": [float(x), float(y), float(w), float(h)]
                })

    elif arr.ndim == 2:
        # Transpose if needed: some YOLO models output (features, anchors) instead of (anchors, features)
        if arr.shape[0] < arr.shape[1]:
            if arr.shape[0] in [5, 6, 7, 8, 84, 85]:
                print(f"[YOLO DEBUG] Transposing from {arr.shape} to {arr.T.shape}")
                arr = arr.T

        print(f"[YOLO DEBUG] Final array shape for parsing: {arr.shape}")

        for row in arr:
            if len(row) >= 5:
                x, y, w, h = row[:4]  # type: ignore[index]
                class_scores = row[4:]  # type: ignore[index]

                # Handle case where row has [x,y,w,h,objectness,class_scores...]
                # vs [x,y,w,h,class_scores...]
                if len(class_scores) == 0:
                    continue

                # If first element of class_scores looks like objectness (> number of classes)
                if len(row) >= 6 and len(YOLO_LABELS) == 1:
                    # Could be [x,y,w,h,objectness,class_score]
                    objectness = float(row[4])
                    actual_scores = row[5:] if len(row) > 5 else row[4:5]
                    class_id = int(np.argmax(actual_scores))
                    confidence = float(actual_scores[class_id])
                    # Use max of objectness * class_conf and plain class_conf
                    effective_conf = max(confidence, objectness * confidence)
                    if effective_conf < YOLO_CONF_THRESHOLD:
                        # Also try objectness alone
                        effective_conf = max(effective_conf, objectness)
                else:
                    class_id = int(np.argmax(class_scores))
                    confidence = float(class_scores[class_id])
                    effective_conf = confidence

                if effective_conf >= YOLO_CONF_THRESHOLD:
                    label = YOLO_LABELS[class_id] if class_id < len(YOLO_LABELS) else f"class_{class_id}"
                    # Convert from center format to corner format for bounding box
                    x1 = float(x - w / 2)
                    y1 = float(y - h / 2)
                    x2 = float(x + w / 2)
                    y2 = float(y + h / 2)
                    detections.append({
                        "label": label,
                        "confidence": round(float(effective_conf), 4),  # pyre-ignore[6]
                        "bbox": [x1, y1, x2, y2],
                        "bbox_center": [float(x), float(y), float(w), float(h)]
                    })

    elif arr.ndim == 3:
        # Shape could be (1, num_detections, features) — squeeze the batch dim
        arr = arr.reshape(-1, arr.shape[-1])
        print(f"[YOLO DEBUG] Reshaped 3D to 2D: {arr.shape}")
        return decode_yolo_output(arr)  # Recurse with 2D array

    print(f"[YOLO DEBUG] Total detections found: {len(detections)}")
    if detections:
        best = max(detections, key=lambda d: d['confidence'])
        print(f"[YOLO DEBUG] Best detection: {best['label']} conf={best['confidence']}")

    return detections

def predict_yolo(image):
    if yolo_interpreter is None:
        return {
            "available": False,
            "detections": [],
            "message": "YOLO model not loaded"
        }

    input_tensor = preprocess_image(image, (640, 640), normalize=True)
    outputs, _, _ = run_tflite(yolo_interpreter, input_tensor)
    raw_output = outputs[0]
    detections = decode_yolo_output(raw_output)

    return {
        "available": True,
        "detections": detections,
        "message": "YOLO inference completed"
    }

# --------------------------------------------------
# XGBOOST LOGIC
# --------------------------------------------------
def extract_wifi_features_from_request(data):
    packet_rate = float(data.get("packet_rate", 0))
    avg_packet_size = float(data.get("avg_packet_size", 0))
    connection_count = float(data.get("connection_count", 0))
    suspicious_port_count = float(data.get("suspicious_port_count", 0))
    signal_strength = float(data.get("signal_strength", 0))
    features = np.array([[packet_rate, avg_packet_size, connection_count, suspicious_port_count, signal_strength]], dtype=np.float32)
    return features

def predict_wifi_risk(data):
    if xgb_model is None:
        return {
            "available": False,
            "network_risk": "Unknown",
            "suspicious_device_found": False,
            "score": 0.0,
            "message": "XGBoost model not loaded"
        }

    features = extract_wifi_features_from_request(data)
    dmatrix = xgb.DMatrix(features)
    pred = xgb_model.predict(dmatrix)
    score = float(pred[0])
    suspicious = score >= 0.5
    risk = "High" if score >= 0.75 else "Medium" if score >= 0.5 else "Low"

    return {
        "available": True,
        "network_risk": risk,
        "suspicious_device_found": suspicious,
        "score": round(float(score), 4),  # pyre-ignore[6]
        "message": "WiFi analysis completed"
    }

# --------------------------------------------------
# FUSION LOGIC
# --------------------------------------------------
def fuse_results(yolo_result, mobilenet_result, wifi_result):
    suspicious_reasons = []

    if yolo_result.get("available") and len(yolo_result.get("detections", [])) > 0:
        suspicious_reasons.append("YOLO detected suspicious object")

    if mobilenet_result.get("available") and mobilenet_result.get("suspicious", False):
        suspicious_reasons.append("MobileNet classified frame as hidden camera")

    if wifi_result.get("available") and wifi_result.get("suspicious_device_found", False):
        suspicious_reasons.append("WiFi traffic model detected suspicious network pattern")

    suspicious = len(suspicious_reasons) > 0

    return {
        "suspicious": suspicious,
        "summary": "Camera Detected" if suspicious else "No Camera Detected",
        "reasons": suspicious_reasons
    }

# --------------------------------------------------
# VIDEO FRAME EXTRACTION
# --------------------------------------------------
def extract_frames_from_video(video_path, max_frames=30, interval=None):
    """Extract frames from a video file at regular intervals."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    if total_frames <= 0:
        return []

    if interval is None:
        # Sample at most max_frames evenly spaced
        if total_frames <= max_frames:
            frame_indices = list(range(total_frames))
        else:
            step = total_frames / max_frames
            frame_indices = [int(step * i) for i in range(max_frames)]
    else:
        frame_indices = list(range(0, total_frames, int(fps * interval)))
        frame_indices = list(frame_indices)[:max_frames]  # pyre-ignore[16]

    frames = []
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            frames.append({
                "frame_index": idx,
                "timestamp": round(float(idx / fps), 2),  # pyre-ignore[6]
                "image": pil_image
            })

    cap.release()
    return frames

def pil_to_base64(image, max_size=(640, 480)):
    """Convert PIL image to base64 string for frontend display."""
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_str}"

# --------------------------------------------------
# AUTH ROUTES (API)
# --------------------------------------------------
@app.route("/api/signup", methods=["POST"])
def api_signup():
    try:
        data = request.get_json()
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "")

        if not username or not email or not password:
            return jsonify({"success": False, "message": "All fields are required"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "message": "Password must be at least 6 characters"}), 400

        # Check existing user
        if users_collection.find_one({"$or": [{"username": username}, {"email": email}]}):
            return jsonify({"success": False, "message": "Username or email already exists"}), 409

        # Hash password
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        user_doc = {
            "username": username,
            "email": email,
            "password": hashed,
            "created_at": datetime.now(timezone.utc)
        }
        users_collection.insert_one(user_doc)

        return jsonify({
            "success": True,
            "message": "Account created successfully"
        }), 201

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"success": False, "message": "Username and password are required"}), 400

        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({"success": False, "message": "Invalid username or password"}), 401

        if not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            return jsonify({"success": False, "message": "Invalid username or password"}), 401

        # Set session
        session["user_id"] = str(user["_id"])
        session["username"] = user["username"]

        return jsonify({
            "success": True,
            "message": "Login successful",
            "user": {
                "username": user["username"],
                "email": user["email"]
            }
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})


@app.route("/api/me", methods=["GET"])
def api_me():
    if "user_id" in session:
        return jsonify({
            "logged_in": True,
            "username": session.get("username", "")
        })
    return jsonify({"logged_in": False})

# --------------------------------------------------
# VIDEO UPLOAD & ANALYSIS API
# --------------------------------------------------
@app.route("/api/upload_video", methods=["POST"])
@login_required
def api_upload_video():
    try:
        if "video" not in request.files:
            return jsonify({"success": False, "message": "No video file provided"}), 400

        video_file = request.files["video"]
        if video_file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Save video temporarily
        ext = os.path.splitext(video_file.filename)[1] or ".mp4"
        temp_filename = f"{uuid.uuid4().hex}{ext}"
        temp_path = os.path.join(app.config["UPLOAD_FOLDER"], temp_filename)
        video_file.save(temp_path)

        try:
            # Extract frames
            frames = extract_frames_from_video(temp_path, max_frames=20)

            if not frames:
                return jsonify({"success": False, "message": "Could not extract frames from video"}), 400

            # Process each frame
            frame_results: list[dict[str, object]] = []
            overall_suspicious = False
            best_detection: dict[str, object] | None = None
            best_confidence: float = 0.0
            all_detections: list[dict[str, object]] = []

            for frame_data in frames:
                image = frame_data["image"]

                # Run all three models
                yolo_result = predict_yolo(image)
                mobilenet_result = predict_mobilenet(image)
                wifi_data = {
                    "packet_rate": 10,
                    "avg_packet_size": 128,
                    "connection_count": 2,
                    "suspicious_port_count": 0,
                    "signal_strength": -45
                }
                wifi_result = predict_wifi_risk(wifi_data)
                fusion = fuse_results(yolo_result, mobilenet_result, wifi_result)

                thumb_b64 = pil_to_base64(image)
                mob_avail = bool(mobilenet_result.get("available", False))
                mob_label = str(mobilenet_result.get("label", "unknown"))
                mob_conf = float(mobilenet_result.get("confidence", 0))
                mob_susp = bool(mobilenet_result.get("suspicious", False))

                frame_entry: dict[str, object] = {
                    "frame_index": frame_data["frame_index"],
                    "timestamp": frame_data["timestamp"],
                    "yolo": yolo_result,
                    "mobilenet": {
                        "available": mob_avail,
                        "label": mob_label,
                        "confidence": mob_conf,
                        "suspicious": mob_susp,
                    },
                    "wifi": wifi_result,
                    "fusion": fusion,
                    "thumbnail": thumb_b64,
                }

                if fusion["suspicious"]:
                    overall_suspicious = True

                # Track best detection for bounding box display
                detections_list = yolo_result.get("detections", [])
                if isinstance(detections_list, list):
                    for det in detections_list:
                        if not isinstance(det, dict):
                            continue
                        all_detections.append({
                            **det,
                            "frame_index": frame_data["frame_index"],
                            "timestamp": frame_data["timestamp"],
                            "thumbnail": thumb_b64,
                        })
                        det_conf = float(det.get("confidence", 0))
                        if det_conf > best_confidence:
                            best_confidence = det_conf
                            best_detection = {
                                **det,
                                "frame_index": frame_data["frame_index"],
                                "timestamp": frame_data["timestamp"],
                                "thumbnail": thumb_b64,
                            }

                frame_results.append(frame_entry)

            # Compute overall confidence
            mob_confs: list[float] = []
            for fr in frame_results:
                mob = fr.get("mobilenet")
                if isinstance(mob, dict) and mob.get("available") and mob.get("suspicious"):
                    mob_confs.append(float(mob.get("confidence", 0)))

            mob_max = max(mob_confs) if mob_confs else 0.0
            raw_confidence: float = max(best_confidence, mob_max) * 100
            overall_confidence: float = round(float(raw_confidence), 1)  # pyre-ignore[6]

            # Build result
            result = {
                "success": True,
                "status": "Camera Detected" if overall_suspicious else "No Camera Detected",
                "suspicious": overall_suspicious,
                "confidence": overall_confidence,
                "total_frames_analyzed": len(frame_results),
                "detections": all_detections,
                "best_detection": best_detection,
                "frame_results": frame_results,
                "video_filename": video_file.filename,
            }

            # Save to MongoDB
            first_thumb = str(frame_results[0].get("thumbnail", "")) if frame_results else None

            scan_doc = {
                "user_id": session["user_id"],
                "username": session.get("username", ""),
                "video_filename": video_file.filename,
                "status": result["status"],
                "suspicious": overall_suspicious,
                "confidence": overall_confidence,
                "total_frames": len(frame_results),
                "detection_count": len(all_detections),
                "detections": list(all_detections)[:10],  # pyre-ignore[16]
                "best_detection": best_detection,
                "timestamp": datetime.now(timezone.utc),
                "thumbnail": first_thumb,
            }
            scan_id = scans_collection.insert_one(scan_doc).inserted_id
            result["scan_id"] = str(scan_id)

            return jsonify(result)

        finally:
            # Clean up temp video file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

# --------------------------------------------------
# SINGLE FRAME ANALYSIS (kept for backward compat)
# --------------------------------------------------
@app.route("/predict_frame", methods=["POST"])
def predict_frame():
    try:
        data = request.get_json()
        if not data or "image" not in data:
            return jsonify({"success": False, "message": "No image received"}), 400

        image = decode_base64_image(data["image"])
        yolo_result = predict_yolo(image)
        mobilenet_result = predict_mobilenet(image)
        wifi_result = predict_wifi_risk(data)
        final_result = fuse_results(yolo_result, mobilenet_result, wifi_result)

        # Build confidence value — always include mobilenet confidence
        mob_conf_raw = float(mobilenet_result.get("confidence", 0))
        mob_is_camera = mobilenet_result.get("label") == "hidden_camera"
        mob_conf = mob_conf_raw if mob_is_camera else 0.0
        yolo_conf = 0.0
        detections = yolo_result.get("detections", [])
        if isinstance(detections, list):
            for det in detections:
                if isinstance(det, dict):
                    yolo_conf = max(yolo_conf, float(det.get("confidence", 0)))
        overall_confidence = round(float(max(mob_conf, yolo_conf) * 100), 1)  # pyre-ignore[6]

        # Save to MongoDB if user is logged in
        scan_id = None
        if "user_id" in session:
            try:
                thumb_b64 = pil_to_base64(image)
                scan_doc = {
                    "user_id": session["user_id"],
                    "username": session.get("username", ""),
                    "video_filename": "Camera Scan",
                    "status": final_result["summary"],
                    "suspicious": final_result["suspicious"],
                    "confidence": overall_confidence,
                    "total_frames": 1,
                    "detection_count": len(detections) if isinstance(detections, list) else 0,
                    "detections": list(detections)[:10] if isinstance(detections, list) else [],  # pyre-ignore[16]
                    "best_detection": detections[0] if isinstance(detections, list) and len(detections) > 0 else None,
                    "timestamp": datetime.now(timezone.utc),
                    "thumbnail": thumb_b64,
                }
                scan_id = str(scans_collection.insert_one(scan_doc).inserted_id)
            except Exception as save_err:
                print(f"Failed to save camera scan to history: {save_err}")

        return jsonify({
            "success": True,
            "final_result": final_result,
            "yolo_result": yolo_result,
            "mobilenet_result": mobilenet_result,
            "wifi_analysis": wifi_result,
            "confidence": overall_confidence,
            "scan_id": scan_id,
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --------------------------------------------------
# LIVE CAMERA DETECT API
# --------------------------------------------------
@app.route("/detect", methods=["POST"])
def detect():
    try:
        data = request.get_json()
        if not data or "image" not in data:
            return jsonify({"detected": False, "object": "none", "confidence": 0, "message": "No image received"}), 400

        image = decode_base64_image(data["image"])

        # Run all models
        yolo_result = predict_yolo(image)
        mobilenet_result = predict_mobilenet(image)
        wifi_result = predict_wifi_risk(data)
        fusion = fuse_results(yolo_result, mobilenet_result, wifi_result)

        # Build confidence — ALWAYS include mobilenet confidence, not just when suspicious
        mob_conf_raw = float(mobilenet_result.get("confidence", 0))
        mob_is_camera = mobilenet_result.get("label") == "hidden_camera"
        mob_conf = mob_conf_raw if mob_is_camera else 0.0

        yolo_conf = 0.0
        detections = yolo_result.get("detections", [])
        if isinstance(detections, list):
            for det in detections:
                if isinstance(det, dict):
                    yolo_conf = max(yolo_conf, float(det.get("confidence", 0)))
        overall_confidence = round(float(max(mob_conf, yolo_conf) * 100), 1)  # pyre-ignore[6]

        detected = fusion["suspicious"]
        obj_label = "hidden_camera" if detected else "none"

        # Pick best label from detections
        if isinstance(detections, list) and len(detections) > 0:
            best_det = max(detections, key=lambda d: float(d.get("confidence", 0)) if isinstance(d, dict) else 0)
            if isinstance(best_det, dict):
                obj_label = best_det.get("label", obj_label)

        return jsonify({
            "detected": detected,
            "object": obj_label,
            "confidence": overall_confidence,
            "summary": fusion["summary"],
            "reasons": fusion.get("reasons", []),
            "models_loaded": {
                "yolo": yolo_interpreter is not None,
                "mobilenet": mobilenet_interpreter is not None,
                "xgboost": xgb_model is not None,
            },
            "yolo": {
                "available": yolo_result.get("available", False),
                "detection_count": len(detections) if isinstance(detections, list) else 0,
                "best_confidence": round(float(yolo_conf * 100), 1),  # pyre-ignore[6]
            },
            "mobilenet": {
                "available": mobilenet_result.get("available", False),
                "label": mobilenet_result.get("label", "unknown"),
                "confidence": round(float(mob_conf_raw * 100), 1),  # pyre-ignore[6]
                "suspicious": mobilenet_result.get("suspicious", False),
            },
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"detected": False, "object": "error", "confidence": 0, "message": str(e)}), 500

# --------------------------------------------------
# HISTORY API
# --------------------------------------------------
@app.route("/api/history", methods=["GET"])
@login_required
def api_history():
    try:
        scans = list(
            scans_collection.find(
                {"user_id": session["user_id"]}
            ).sort("timestamp", -1).limit(50)
        )

        history = []
        for scan in scans:
            history.append({
                "id": str(scan["_id"]),
                "video_filename": scan.get("video_filename", "Unknown"),
                "status": scan.get("status", "Unknown"),
                "suspicious": scan.get("suspicious", False),
                "confidence": scan.get("confidence", 0),
                "total_frames": scan.get("total_frames", 0),
                "detection_count": scan.get("detection_count", 0),
                "timestamp": scan.get("timestamp", datetime.now(timezone.utc)).strftime("%d %b, %Y %H:%M"),
                "thumbnail": scan.get("thumbnail")
            })

        return jsonify({"success": True, "history": history})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/history/<scan_id>", methods=["GET"])
@login_required
def api_history_detail(scan_id):
    try:
        scan = scans_collection.find_one({
            "_id": ObjectId(scan_id),
            "user_id": session["user_id"]
        })

        if not scan:
            return jsonify({"success": False, "message": "Scan not found"}), 404

        return jsonify({
            "success": True,
            "scan": {
                "id": str(scan["_id"]),
                "video_filename": scan.get("video_filename", "Unknown"),
                "status": scan.get("status", "Unknown"),
                "suspicious": scan.get("suspicious", False),
                "confidence": scan.get("confidence", 0),
                "total_frames": scan.get("total_frames", 0),
                "detection_count": scan.get("detection_count", 0),
                "detections": scan.get("detections", []),
                "best_detection": scan.get("best_detection"),
                "timestamp": scan.get("timestamp", datetime.now(timezone.utc)).strftime("%d %b, %Y %H:%M"),
                "thumbnail": scan.get("thumbnail")
            }
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/history/<scan_id>", methods=["DELETE"])
@login_required
def api_history_delete(scan_id):
    try:
        result = scans_collection.delete_one({
            "_id": ObjectId(scan_id),
            "user_id": session["user_id"]
        })
        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "Scan not found"}), 404

        return jsonify({"success": True, "message": "Scan deleted"})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --------------------------------------------------
# MODEL STATUS DIAGNOSTIC ENDPOINT
# --------------------------------------------------
@app.route("/api/model_status", methods=["GET"])
def api_model_status():
    """Diagnostic endpoint to check if all AI models are loaded."""
    status = {
        "yolo": {
            "loaded": yolo_interpreter is not None,
            "path": YOLO_MODEL_PATH,
            "file_exists": os.path.exists(YOLO_MODEL_PATH),
        },
        "mobilenet": {
            "loaded": mobilenet_interpreter is not None,
            "path": MOBILENET_MODEL_PATH,
            "file_exists": os.path.exists(MOBILENET_MODEL_PATH),
        },
        "xgboost": {
            "loaded": xgb_model is not None,
            "path": XGB_MODEL_PATH,
            "file_exists": os.path.exists(XGB_MODEL_PATH),
        },
    }

    # Also inspect model input/output shapes if loaded
    if yolo_interpreter:
        inp = yolo_interpreter.get_input_details()
        out = yolo_interpreter.get_output_details()
        status["yolo"]["input_shape"] = str(inp[0]["shape"].tolist()) if inp else "N/A"
        status["yolo"]["output_shape"] = str(out[0]["shape"].tolist()) if out else "N/A"
        status["yolo"]["input_dtype"] = str(inp[0]["dtype"]) if inp else "N/A"

    if mobilenet_interpreter:
        inp = mobilenet_interpreter.get_input_details()
        out = mobilenet_interpreter.get_output_details()
        status["mobilenet"]["input_shape"] = str(inp[0]["shape"].tolist()) if inp else "N/A"
        status["mobilenet"]["output_shape"] = str(out[0]["shape"].tolist()) if out else "N/A"
        status["mobilenet"]["input_dtype"] = str(inp[0]["dtype"]) if inp else "N/A"

    all_loaded = all(s["loaded"] for s in status.values())
    return jsonify({"success": True, "all_loaded": all_loaded, "models": status})

# --------------------------------------------------
# PAGE ROUTES
# --------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/signup")
def signup():
    return render_template("signup.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/history")
@login_required
def history():
    return render_template("history.html")

@app.route("/reports")
@login_required
def reports():
    # Fetch from MongoDB
    scans = list(
        scans_collection.find(
            {"user_id": session.get("user_id", "")}
        ).sort("timestamp", -1).limit(20)
    )

    reports_data = []
    for scan in scans:
        reports_data.append({
            "date": scan.get("timestamp", datetime.now(timezone.utc)).strftime("%d %b, %Y"),
            "status": "Detected" if scan.get("suspicious") else "Safe",
            "confidence": f"{scan.get('confidence', 0)}%",
            "location": scan.get("video_filename", "Unknown")
        })

    if not reports_data:
        reports_data = [
            {"date": "No scans yet", "status": "Safe", "confidence": "0%", "location": "N/A"}
        ]

    return render_template("reports.html", reports=reports_data)

@app.route("/scan")
def scan():
    return render_template("scan.html")
# --------------------------------------------------
# STARTUP LOGGING (runs under both gunicorn and direct python)
# --------------------------------------------------
print("=" * 50)
print("SmartCam Shield starting...")
print(f"YOLO model: {'Loaded' if yolo_interpreter else 'NOT LOADED'}")
print(f"MobileNet model: {'Loaded' if mobilenet_interpreter else 'NOT LOADED'}")
print(f"XGBoost model: {'Loaded' if xgb_model else 'NOT LOADED'}")
print(f"YOLO path exists: {os.path.exists(YOLO_MODEL_PATH)} ({YOLO_MODEL_PATH})")
print(f"MobileNet path exists: {os.path.exists(MOBILENET_MODEL_PATH)} ({MOBILENET_MODEL_PATH})")
print(f"XGBoost path exists: {os.path.exists(XGB_MODEL_PATH)} ({XGB_MODEL_PATH})")
print("=" * 50)

# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    print("\nRegistered routes:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.rule:40s} -> {rule.endpoint:30s} methods={rule.methods}")
    print("=" * 50)
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)