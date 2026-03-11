/* ========================================
   SMARTCAM SHIELD — MAIN JAVASCRIPT
   ======================================== */

// ==========================================
// UTILITY FUNCTIONS
// ==========================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 4000);
}

function setLoading(btn, loading) {
    if (!btn) return;
    const text = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.btn-loader');
    if (text) text.style.display = loading ? 'none' : '';
    if (loader) loader.style.display = loading ? 'inline-block' : 'none';
    btn.disabled = loading;
}

// ==========================================
// AUTH STATE MANAGEMENT
// ==========================================

async function checkAuthState() {
    try {
        const resp = await fetch('/api/me');
        const data = await resp.json();

        const authOnlyLinks = document.querySelectorAll('.nav-auth-only');
        const loginBtn = document.getElementById('navLoginBtn');
        const signupBtn = document.getElementById('navSignupBtn');
        const userInfo = document.getElementById('navUserInfo');
        const username = document.getElementById('navUsername');

        if (data.logged_in) {
            authOnlyLinks.forEach(el => el.style.display = '');
            if (loginBtn) loginBtn.style.display = 'none';
            if (signupBtn) signupBtn.style.display = 'none';
            if (userInfo) {
                userInfo.style.display = 'flex';
                if (username) username.textContent = data.username;
            }
        } else {
            authOnlyLinks.forEach(el => el.style.display = 'none');
            if (loginBtn) loginBtn.style.display = '';
            if (signupBtn) signupBtn.style.display = '';
            if (userInfo) userInfo.style.display = 'none';
        }
    } catch (e) {
        console.error('Auth check failed:', e);
    }
}

// Logout handler
document.addEventListener('DOMContentLoaded', () => {
    const logoutBtn = document.getElementById('navLogoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                await fetch('/api/logout', { method: 'POST' });
                showToast('Logged out successfully', 'success');
                setTimeout(() => { window.location.href = '/'; }, 800);
            } catch (e) {
                showToast('Logout failed', 'error');
            }
        });
    }

    checkAuthState();
});

// ==========================================
// LOGIN PAGE
// ==========================================

const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const btn = document.getElementById('loginSubmitBtn');
        const errorEl = document.getElementById('loginError');
        const username = document.getElementById('loginUsername').value.trim();
        const password = document.getElementById('loginPassword').value;

        if (errorEl) errorEl.style.display = 'none';

        if (!username || !password) {
            if (errorEl) {
                errorEl.textContent = 'Please fill in all fields';
                errorEl.style.display = 'block';
            }
            return;
        }

        setLoading(btn, true);

        try {
            const resp = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const data = await resp.json();

            if (data.success) {
                showToast('Login successful! Redirecting...', 'success');
                setTimeout(() => { window.location.href = '/dashboard'; }, 1000);
            } else {
                if (errorEl) {
                    errorEl.textContent = data.message || 'Login failed';
                    errorEl.style.display = 'block';
                }
                showToast(data.message || 'Login failed', 'error');
            }
        } catch (err) {
            showToast('Server error. Please try again.', 'error');
            if (errorEl) {
                errorEl.textContent = 'Connection error. Please try again.';
                errorEl.style.display = 'block';
            }
        } finally {
            setLoading(btn, false);
        }
    });
}

// ==========================================
// SIGNUP PAGE
// ==========================================

const signupForm = document.getElementById('signupForm');
if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const btn = document.getElementById('signupSubmitBtn');
        const errorEl = document.getElementById('signupError');
        const username = document.getElementById('signupUsername').value.trim();
        const email = document.getElementById('signupEmail').value.trim();
        const password = document.getElementById('signupPassword').value;

        if (errorEl) errorEl.style.display = 'none';

        if (!username || !email || !password) {
            if (errorEl) {
                errorEl.textContent = 'Please fill in all fields';
                errorEl.style.display = 'block';
            }
            return;
        }

        if (password.length < 6) {
            if (errorEl) {
                errorEl.textContent = 'Password must be at least 6 characters';
                errorEl.style.display = 'block';
            }
            return;
        }

        setLoading(btn, true);

        try {
            const resp = await fetch('/api/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, email, password })
            });

            const data = await resp.json();

            if (data.success) {
                showToast('Account created! Redirecting to login...', 'success');
                setTimeout(() => { window.location.href = '/login'; }, 1200);
            } else {
                if (errorEl) {
                    errorEl.textContent = data.message || 'Signup failed';
                    errorEl.style.display = 'block';
                }
                showToast(data.message || 'Signup failed', 'error');
            }
        } catch (err) {
            showToast('Server error. Please try again.', 'error');
            if (errorEl) {
                errorEl.textContent = 'Connection error. Please try again.';
                errorEl.style.display = 'block';
            }
        } finally {
            setLoading(btn, false);
        }
    });
}

// ==========================================
// DASHBOARD — VIDEO UPLOAD & DETECTION
// ==========================================

const uploadZone = document.getElementById('uploadZone');
const videoFileInput = document.getElementById('videoFileInput');
const videoPreviewArea = document.getElementById('videoPreviewArea');
const videoPreview = document.getElementById('videoPreview');
const videoFilename = document.getElementById('videoFilename');
const removeVideoBtn = document.getElementById('removeVideoBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const analysisProgress = document.getElementById('analysisProgress');
const analysisProgressFill = document.getElementById('analysisProgressFill');
const progressPercent = document.getElementById('progressPercent');
const progressStatus = document.getElementById('progressStatus');
const resultsEmpty = document.getElementById('resultsEmpty');
const resultsContent = document.getElementById('resultsContent');

let selectedVideoFile = null;

if (uploadZone) {
    // Drag and drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('video/')) {
            handleVideoSelection(files[0]);
        } else {
            showToast('Please drop a valid video file', 'error');
        }
    });
}

if (videoFileInput) {
    videoFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleVideoSelection(e.target.files[0]);
        }
    });
}

function handleVideoSelection(file) {
    if (file.size > 100 * 1024 * 1024) {
        showToast('File too large. Max 100MB.', 'error');
        return;
    }

    selectedVideoFile = file;

    if (videoFilename) videoFilename.textContent = file.name;
    if (videoPreview) {
        const url = URL.createObjectURL(file);
        videoPreview.src = url;
    }
    if (uploadZone) uploadZone.style.display = 'none';
    if (videoPreviewArea) videoPreviewArea.style.display = 'block';
    if (analyzeBtn) analyzeBtn.disabled = false;

    // Reset results
    if (resultsEmpty) resultsEmpty.style.display = '';
    if (resultsContent) resultsContent.style.display = 'none';
}

if (removeVideoBtn) {
    removeVideoBtn.addEventListener('click', () => {
        selectedVideoFile = null;
        if (videoPreview) videoPreview.src = '';
        if (uploadZone) uploadZone.style.display = '';
        if (videoPreviewArea) videoPreviewArea.style.display = 'none';
        if (analyzeBtn) analyzeBtn.disabled = true;
        if (videoFileInput) videoFileInput.value = '';
        if (resultsEmpty) resultsEmpty.style.display = '';
        if (resultsContent) resultsContent.style.display = 'none';
        if (analysisProgress) analysisProgress.style.display = 'none';
    });
}

if (analyzeBtn) {
    analyzeBtn.addEventListener('click', async () => {
        if (!selectedVideoFile) return;

        setLoading(analyzeBtn, true);
        if (analysisProgress) analysisProgress.style.display = '';
        if (analysisProgressFill) analysisProgressFill.style.width = '0%';
        if (progressPercent) progressPercent.textContent = '0%';
        if (progressStatus) progressStatus.textContent = 'Uploading video...';
        if (resultsEmpty) resultsEmpty.style.display = 'none';
        if (resultsContent) resultsContent.style.display = 'none';

        // Fake progress
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += Math.random() * 8;
            if (progress > 90) progress = 90;
            if (analysisProgressFill) analysisProgressFill.style.width = progress + '%';
            if (progressPercent) progressPercent.textContent = Math.round(progress) + '%';

            if (progress > 20 && progress < 50) {
                if (progressStatus) progressStatus.textContent = 'Extracting video frames...';
            } else if (progress >= 50 && progress < 75) {
                if (progressStatus) progressStatus.textContent = 'Running AI model analysis...';
            } else if (progress >= 75) {
                if (progressStatus) progressStatus.textContent = 'Fusing model results...';
            }
        }, 400);

        try {
            const formData = new FormData();
            formData.append('video', selectedVideoFile);

            const resp = await fetch('/api/upload_video', {
                method: 'POST',
                body: formData
            });

            clearInterval(progressInterval);

            const data = await resp.json();

            if (data.success) {
                if (analysisProgressFill) analysisProgressFill.style.width = '100%';
                if (progressPercent) progressPercent.textContent = '100%';
                if (progressStatus) progressStatus.textContent = 'Analysis complete!';

                setTimeout(() => {
                    if (analysisProgress) analysisProgress.style.display = 'none';
                    displayResults(data);
                }, 600);

                showToast('Analysis complete!', 'success');
            } else {
                if (analysisProgress) analysisProgress.style.display = 'none';
                showToast(data.message || 'Analysis failed', 'error');
                if (resultsEmpty) resultsEmpty.style.display = '';
            }
        } catch (err) {
            clearInterval(progressInterval);
            if (analysisProgress) analysisProgress.style.display = 'none';
            showToast('Server error during analysis', 'error');
            if (resultsEmpty) resultsEmpty.style.display = '';
        } finally {
            setLoading(analyzeBtn, false);
        }
    });
}

function displayResults(data) {
    if (resultsContent) resultsContent.style.display = '';
    if (resultsEmpty) resultsEmpty.style.display = 'none';

    // Status banner
    const banner = document.getElementById('resultStatusBanner');
    const statusIcon = document.getElementById('statusIcon');
    const statusLabel = document.getElementById('statusLabel');
    const statusConfidence = document.getElementById('statusConfidence');

    if (banner) {
        banner.className = 'result-status-banner ' + (data.suspicious ? 'detected' : 'safe');
    }
    if (statusIcon) statusIcon.textContent = data.suspicious ? '🚨' : '✅';
    if (statusLabel) statusLabel.textContent = data.status;
    if (statusConfidence) statusConfidence.textContent = `Confidence: ${data.confidence}%`;

    // Model breakdown
    const yoloValue = document.getElementById('yoloValue');
    const mobilenetValue = document.getElementById('mobilenetValue');
    const xgboostValue = document.getElementById('xgboostValue');

    const detectionsCount = data.detections ? data.detections.length : 0;

    if (yoloValue) {
        yoloValue.textContent = detectionsCount > 0 ? `${detectionsCount} detection(s)` : 'No detections';
        yoloValue.className = 'model-value ' + (detectionsCount > 0 ? 'detected' : 'safe');
    }

    // Get mobilenet info from first frame
    if (mobilenetValue && data.frame_results && data.frame_results.length > 0) {
        const mob = data.frame_results[0].mobilenet;
        if (mob && mob.available) {
            mobilenetValue.textContent = `${mob.label} (${(mob.confidence * 100).toFixed(1)}%)`;
            mobilenetValue.className = 'model-value ' + (mob.suspicious ? 'detected' : 'safe');
        }
    }

    if (xgboostValue && data.frame_results && data.frame_results.length > 0) {
        const wifi = data.frame_results[0].wifi;
        if (wifi && wifi.available) {
            xgboostValue.textContent = `${wifi.network_risk} Risk (${(wifi.score * 100).toFixed(1)}%)`;
            xgboostValue.className = 'model-value ' + (wifi.suspicious_device_found ? 'detected' : 'safe');
        }
    }

    // Frame details
    const frameDetails = document.getElementById('frameDetails');
    const totalFrames = document.getElementById('totalFrames');
    const totalDetections = document.getElementById('totalDetections');

    if (frameDetails) frameDetails.style.display = '';
    if (totalFrames) totalFrames.textContent = data.total_frames_analyzed || 0;
    if (totalDetections) totalDetections.textContent = detectionsCount;

    // Detection reasons
    const reasonsDiv = document.getElementById('detectionReasons');
    const reasonsList = document.getElementById('reasonsList');

    if (data.suspicious && data.frame_results) {
        // Collect all unique reasons
        const allReasons = new Set();
        data.frame_results.forEach(fr => {
            if (fr.fusion && fr.fusion.reasons) {
                fr.fusion.reasons.forEach(r => allReasons.add(r));
            }
        });

        if (allReasons.size > 0 && reasonsDiv && reasonsList) {
            reasonsDiv.style.display = '';
            reasonsList.innerHTML = '';
            allReasons.forEach(reason => {
                const li = document.createElement('li');
                li.textContent = reason;
                reasonsList.appendChild(li);
            });
        }
    } else if (reasonsDiv) {
        reasonsDiv.style.display = 'none';
    }

    // Draw bounding box if detection exists
    if (data.best_detection && data.best_detection.thumbnail) {
        drawBoundingBox(data.best_detection);
    }
}

function drawBoundingBox(detection) {
    const canvasWrap = document.getElementById('detectionCanvasWrap');
    const canvas = document.getElementById('detectionCanvas');
    if (!canvasWrap || !canvas) return;

    canvasWrap.style.display = '';

    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = () => {
        canvas.width = img.width;
        canvas.height = img.height;

        // Draw image
        ctx.drawImage(img, 0, 0);

        // Draw bounding box
        const bbox = detection.bbox;
        if (bbox && bbox.length === 4) {
            // bbox is [x1, y1, x2, y2] in YOLO 640x640 space
            // Scale to actual image dimensions
            const scaleX = img.width / 640;
            const scaleY = img.height / 640;

            const x1 = bbox[0] * scaleX;
            const y1 = bbox[1] * scaleY;
            const x2 = bbox[2] * scaleX;
            const y2 = bbox[3] * scaleY;

            const w = x2 - x1;
            const h = y2 - y1;

            // Bounding box
            ctx.strokeStyle = '#ff3b3b';
            ctx.lineWidth = 3;
            ctx.setLineDash([]);
            ctx.strokeRect(x1, y1, w, h);

            // Corner accents
            const cornerLen = Math.min(20, w / 4, h / 4);
            ctx.strokeStyle = '#f0c861';
            ctx.lineWidth = 4;

            // Top-left
            ctx.beginPath();
            ctx.moveTo(x1, y1 + cornerLen);
            ctx.lineTo(x1, y1);
            ctx.lineTo(x1 + cornerLen, y1);
            ctx.stroke();

            // Top-right
            ctx.beginPath();
            ctx.moveTo(x2 - cornerLen, y1);
            ctx.lineTo(x2, y1);
            ctx.lineTo(x2, y1 + cornerLen);
            ctx.stroke();

            // Bottom-left
            ctx.beginPath();
            ctx.moveTo(x1, y2 - cornerLen);
            ctx.lineTo(x1, y2);
            ctx.lineTo(x1 + cornerLen, y2);
            ctx.stroke();

            // Bottom-right
            ctx.beginPath();
            ctx.moveTo(x2 - cornerLen, y2);
            ctx.lineTo(x2, y2);
            ctx.lineTo(x2, y2 - cornerLen);
            ctx.stroke();

            // Label background
            const label = `${detection.label} ${(detection.confidence * 100).toFixed(1)}%`;
            ctx.font = 'bold 14px Inter, Arial, sans-serif';
            const textWidth = ctx.measureText(label).width;
            const labelPadding = 6;
            const labelHeight = 22;

            ctx.fillStyle = 'rgba(255, 59, 59, 0.85)';
            ctx.fillRect(x1, y1 - labelHeight - 4, textWidth + labelPadding * 2, labelHeight);

            ctx.fillStyle = '#ffffff';
            ctx.textBaseline = 'middle';
            ctx.fillText(label, x1 + labelPadding, y1 - labelHeight / 2 - 4);
        }
    };

    img.src = detection.thumbnail;
}

// ==========================================
// HISTORY PAGE
// ==========================================

const historyList = document.getElementById('historyList');
const historyLoading = document.getElementById('historyLoading');
const historyEmpty = document.getElementById('historyEmpty');
const detailModal = document.getElementById('detailModal');
const modalClose = document.getElementById('modalClose');
const modalBody = document.getElementById('modalBody');

if (historyList) {
    loadHistory();
}

async function loadHistory() {
    try {
        const resp = await fetch('/api/history');
        const data = await resp.json();

        if (historyLoading) historyLoading.style.display = 'none';

        if (!data.success || !data.history || data.history.length === 0) {
            if (historyEmpty) historyEmpty.style.display = '';
            return;
        }

        if (historyList) {
            historyList.style.display = '';
            historyList.innerHTML = '';

            data.history.forEach(item => {
                const div = document.createElement('div');
                div.className = 'history-item';
                div.innerHTML = `
                    ${item.thumbnail ?
                        `<img class="history-thumb" src="${item.thumbnail}" alt="Scan thumbnail">` :
                        `<div class="history-thumb" style="display:flex;align-items:center;justify-content:center;color:#6b5c36;font-size:1.2rem;">📹</div>`
                    }
                    <div class="history-info">
                        <div class="history-filename">${escapeHtml(item.video_filename)}</div>
                        <div class="history-date">${item.timestamp}</div>
                    </div>
                    <span class="history-status ${item.suspicious ? 'detected' : 'safe'}">
                        ${item.suspicious ? 'Detected' : 'Safe'}
                    </span>
                    <span class="history-confidence">${item.confidence}%</span>
                    <button class="history-delete" data-id="${item.id}" title="Delete">🗑️</button>
                    <span class="history-arrow">›</span>
                `;

                // Click to show details (but not on delete button)
                div.addEventListener('click', (e) => {
                    if (e.target.classList.contains('history-delete')) return;
                    showScanDetail(item.id);
                });

                // Delete handler
                const deleteBtn = div.querySelector('.history-delete');
                if (deleteBtn) {
                    deleteBtn.addEventListener('click', async (e) => {
                        e.stopPropagation();
                        if (!confirm('Delete this scan record?')) return;

                        try {
                            const delResp = await fetch(`/api/history/${item.id}`, { method: 'DELETE' });
                            const delData = await delResp.json();
                            if (delData.success) {
                                div.remove();
                                showToast('Scan deleted', 'success');
                                // Check if list is now empty
                                if (historyList.children.length === 0) {
                                    historyList.style.display = 'none';
                                    if (historyEmpty) historyEmpty.style.display = '';
                                }
                            }
                        } catch (err) {
                            showToast('Failed to delete scan', 'error');
                        }
                    });
                }

                historyList.appendChild(div);
            });
        }
    } catch (err) {
        if (historyLoading) historyLoading.style.display = 'none';
        showToast('Failed to load history', 'error');
        if (historyEmpty) historyEmpty.style.display = '';
    }
}

async function showScanDetail(scanId) {
    if (!detailModal || !modalBody) return;

    detailModal.style.display = '';
    modalBody.innerHTML = '<div class="history-loading" style="padding:30px;"><div class="loading-spinner"></div><p>Loading details...</p></div>';

    try {
        const resp = await fetch(`/api/history/${scanId}`);
        const data = await resp.json();

        if (!data.success) {
            modalBody.innerHTML = '<p style="color:#ff6b6b;">Failed to load scan details.</p>';
            return;
        }

        const scan = data.scan;
        let html = '';

        if (scan.thumbnail) {
            html += `<img class="modal-thumb-large" src="${scan.thumbnail}" alt="Scan frame">`;
        }

        html += `
            <div class="detail-row">
                <span class="detail-label">Video File</span>
                <span class="detail-value">${escapeHtml(scan.video_filename)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Status</span>
                <span class="detail-value" style="color:${scan.suspicious ? '#ff6b6b' : '#35d06d'}">
                    ${scan.status}
                </span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Confidence</span>
                <span class="detail-value" style="color:#f0c861">${scan.confidence}%</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Frames Analyzed</span>
                <span class="detail-value">${scan.total_frames}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Detections</span>
                <span class="detail-value">${scan.detection_count}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Scanned At</span>
                <span class="detail-value">${scan.timestamp}</span>
            </div>
        `;

        if (scan.detections && scan.detections.length > 0) {
            html += '<h3 style="color:#f0c861;margin:16px 0 10px;font-size:1rem;">Detection Details</h3>';
            scan.detections.forEach((det, i) => {
                html += `
                    <div style="background:rgba(255,59,59,0.05);border:1px solid rgba(255,76,76,0.12);border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:0.85rem;color:#c4b88a;">
                        <strong style="color:#ff6b6b;">#${i + 1} ${escapeHtml(det.label)}</strong>
                        — Confidence: ${(det.confidence * 100).toFixed(1)}%
                        ${det.timestamp !== undefined ? ` | Frame time: ${det.timestamp}s` : ''}
                    </div>
                `;
            });
        }

        modalBody.innerHTML = html;

    } catch (err) {
        modalBody.innerHTML = '<p style="color:#ff6b6b;">Error loading scan details.</p>';
    }
}

if (modalClose) {
    modalClose.addEventListener('click', () => {
        if (detailModal) detailModal.style.display = 'none';
    });
}

if (detailModal) {
    detailModal.addEventListener('click', (e) => {
        if (e.target === detailModal) {
            detailModal.style.display = 'none';
        }
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// ==========================================
// SCAN PAGE (kept for backward compat)
// ==========================================

const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const startCameraBtn = document.getElementById("startCameraBtn");
const captureBtn = document.getElementById("captureBtn");
const stopCameraBtn = document.getElementById("stopCameraBtn");
const continueBtn = document.getElementById("continueBtn");

const resultBox = document.getElementById("resultBox");
const scanTitle = document.getElementById("scanTitle");
const scanRing = document.getElementById("scanRing");
const scanProgressArea = document.getElementById("scanProgressArea");
const scanSuccessArea = document.getElementById("scanSuccessArea");
const scanProgressFill = document.getElementById("scanProgressFill");
const scanStatusText = document.getElementById("scanStatusText");
const scanSubText = document.getElementById("scanSubText");

let currentStream = null;
let fakeProgressInterval = null;

async function startCamera() {
    if (!video) return;

    try {
        currentStream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: false
        });

        video.srcObject = currentStream;
        await video.play();

        if (resultBox) {
            resultBox.innerHTML = "<p>Camera started successfully.</p>";
        }
    } catch (error) {
        console.error("Camera access error:", error);

        if (resultBox) {
            resultBox.innerHTML = "<p>Unable to access camera. Please allow camera permissions.</p>";
        }
    }
}

function stopCamera() {
    if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
        currentStream = null;
    }

    if (video) {
        video.srcObject = null;
    }

    resetScanUI();

    if (resultBox) {
        resultBox.innerHTML = "<p>Camera stopped.</p>";
    }
}

function resetScanUI() {
    if (scanTitle) scanTitle.textContent = "SCAN INITIATED";

    if (scanRing) {
        scanRing.classList.remove("success");
        scanRing.classList.add("scanning");
    }

    if (scanProgressArea) scanProgressArea.style.display = "block";
    if (scanSuccessArea) scanSuccessArea.style.display = "none";
    if (scanProgressFill) scanProgressFill.style.width = "0%";
    if (scanStatusText) scanStatusText.textContent = "SCANNING...";
    if (scanSubText) scanSubText.textContent = "PLEASE WAIT";

    if (fakeProgressInterval) {
        clearInterval(fakeProgressInterval);
        fakeProgressInterval = null;
    }
}

function startFakeProgress() {
    let progress = 0;

    if (scanProgressFill) {
        scanProgressFill.style.width = "0%";
    }

    fakeProgressInterval = setInterval(() => {
        if (progress < 88) {
            progress += Math.random() * 12;
            if (scanProgressFill) {
                scanProgressFill.style.width = `${Math.min(progress, 88)}%`;
            }
        }
    }, 300);
}

function finishScanUI() {
    if (fakeProgressInterval) {
        clearInterval(fakeProgressInterval);
        fakeProgressInterval = null;
    }

    if (scanProgressFill) scanProgressFill.style.width = "100%";
    if (scanTitle) scanTitle.textContent = "SCAN COMPLETE";

    setTimeout(() => {
        if (scanRing) {
            scanRing.classList.remove("scanning");
            scanRing.classList.add("success");
        }

        if (scanProgressArea) scanProgressArea.style.display = "none";
        if (scanSuccessArea) scanSuccessArea.style.display = "block";
    }, 600);
}

async function captureAndAnalyze() {
    if (!video || !canvas) return;

    if (!video.srcObject) {
        if (resultBox) {
            resultBox.innerHTML = "<p>Please start the camera first.</p>";
        }
        return;
    }

    resetScanUI();
    startFakeProgress();

    const context = canvas.getContext("2d");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    const imageData = canvas.toDataURL("image/jpeg");

    const payload = {
        image: imageData,
        packet_rate: 10,
        avg_packet_size: 128,
        connection_count: 2,
        suspicious_port_count: 0,
        signal_strength: -45
    };

    if (resultBox) {
        resultBox.innerHTML = "<p>Analyzing frame...</p>";
    }

    try {
        const response = await fetch("/predict_frame", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!result.success) {
            if (fakeProgressInterval) {
                clearInterval(fakeProgressInterval);
                fakeProgressInterval = null;
            }

            if (scanProgressFill) scanProgressFill.style.width = "0%";
            if (scanStatusText) scanStatusText.textContent = "SCAN FAILED";
            if (scanSubText) scanSubText.textContent = "TRY AGAIN";

            if (resultBox) {
                resultBox.innerHTML = `<p>Analysis failed: ${result.message}</p>`;
            }

            return;
        }

        finishScanUI();

        const finalResult = result.final_result;
        const yolo = result.yolo_result;
        const mobilenet = result.mobilenet_result;
        const wifi = result.wifi_analysis;

        if (resultBox) {
            resultBox.innerHTML = `
                <h3>Final Summary</h3>
                <p><strong>Status:</strong> ${finalResult.summary}</p>
                <p><strong>Suspicious:</strong> ${finalResult.suspicious ? "Yes" : "No"}</p>
                <p><strong>Reasons:</strong> ${finalResult.reasons.length ? finalResult.reasons.join(", ") : "None"}</p>

                <hr>

                <h3>YOLO Detection</h3>
                <p><strong>Available:</strong> ${yolo.available ? "Yes" : "No"}</p>
                <p><strong>Detections:</strong> ${yolo.detections.length}</p>

                <hr>

                <h3>MobileNet Classification</h3>
                <p><strong>Label:</strong> ${mobilenet.label}</p>
                <p><strong>Confidence:</strong> ${mobilenet.confidence}</p>

                <hr>

                <h3>WiFi Analysis</h3>
                <p><strong>Risk:</strong> ${wifi.network_risk}</p>
                <p><strong>Score:</strong> ${wifi.score}</p>
            `;
        }
    } catch (error) {
        console.error("Prediction error:", error);

        if (fakeProgressInterval) {
            clearInterval(fakeProgressInterval);
            fakeProgressInterval = null;
        }

        if (scanStatusText) scanStatusText.textContent = "SCAN FAILED";
        if (scanSubText) scanSubText.textContent = "SERVER ERROR";

        if (resultBox) {
            resultBox.innerHTML = "<p>Server error while analyzing frame.</p>";
        }
    }
}

if (startCameraBtn) {
    startCameraBtn.addEventListener("click", startCamera);
}

if (captureBtn) {
    captureBtn.addEventListener("click", captureAndAnalyze);
}

if (stopCameraBtn) {
    stopCameraBtn.addEventListener("click", stopCamera);
}

if (continueBtn) {
    continueBtn.addEventListener("click", () => {
        window.location.href = "/reports";
    });
}