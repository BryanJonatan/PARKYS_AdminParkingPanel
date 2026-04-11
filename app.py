from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import requests
import re
import config
from services.scanner import scan_plate
import cv2
import threading

app = Flask(__name__)
app.secret_key = "raspberry-secret-key"

API_BASE = config.BACKEND_URL


camera = cv2.VideoCapture('/dev/video1', cv2.CAP_V4L2)
if not camera.isOpened():
    camera = cv2.VideoCapture('/dev/video0', cv2.CAP_V4L2)

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

lock = threading.Lock()

def gen_frames():
    while True:
        with lock:
            success, frame = camera.read()
        if not success:
            continue
        
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def normalize_plate(plate: str) -> str:
    return re.sub(r'\s+', '', plate.strip().upper())

# --- ROUTES ---
@app.route("/logout")
def logout():
    print("[LOGOUT] clearing session")
    session.clear()
    return redirect(url_for("login"))
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email, password = request.form.get("email"), request.form.get("password")
        resp = requests.post(f"{API_BASE}/api/parkirAdmin/verify-admin", json={"email": email, "password": password})
        if resp.status_code == 200:
            data = resp.json()
            session.update({"admin_email": email, "admin_user_id": data.get("UserId")})
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Login gagal.")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "admin_email" not in session: return redirect(url_for("login"))
    return render_template("dashboard.html", admin_email=session.get("admin_email"))

@app.route("/scan-and-create", methods=["POST"])
def scan_and_create():
    if "admin_email" not in session:
        return jsonify({"success": False}), 401

    raw_plate = scan_plate(camera)
    if not raw_plate:
        return jsonify({"success": False, "message": "Plat tidak terdeteksi."})

    plate = normalize_plate(raw_plate)

    payload = {
        "adminUserId": int(session.get("admin_user_id")),
        "nomorPlat": plate
    }

    resp = requests.post(f"{API_BASE}/api/v1/webcam-parkir/create", json=payload)

    if resp.status_code != 200:
        return jsonify({
            "success": False,
            "message": "Gagal ke Backend.",
            "plate": plate
        })

    backend_data = resp.json()
    return jsonify({
        "success": backend_data.get("success", False),
        "message": backend_data.get("message"),
        "plate": plate
    })

@app.route("/scan-and-complete", methods=["POST"])
def scan_and_complete():
    if "admin_email" not in session:
        return jsonify({"success": False}), 401

    raw_plate = scan_plate(camera)
    if not raw_plate:
        return jsonify({"success": False, "message": "Plat tidak terdeteksi."})

    plate = normalize_plate(raw_plate)

    payload = {
        "adminParkingId": int(session.get("admin_user_id")),
        "nomorPlat": plate
    }

    resp = requests.post(f"{API_BASE}/api/v1/webcam-parkir/complete", json=payload)

    if resp.status_code != 200:
        return jsonify({
            "success": False,
            "message": "Gagal proses keluar.",
            "plate": plate
        })

    backend_data = resp.json()

    return jsonify({
        "success": backend_data.get("success", False),
        "message": backend_data.get("message"),
        "plate": plate
    })

@app.route("/create")
def create_parkir(): return render_template("create_parkir.html") if "admin_email" in session else redirect(url_for("login"))

@app.route("/complete")
def complete_parkir(): return render_template("complete_parkir.html") if "admin_email" in session else redirect(url_for("login"))

@app.route("/data-parkir")
def data_parkir():
    if "admin_email" not in session: return redirect(url_for("login"))
    
    admin_user_id = int(session.get("admin_user_id"))
    resp = requests.get(
        f"{API_BASE}/api/parkirAdmin/data-parkir", 
        params={"adminUserId": admin_user_id}
    )
    parkings = resp.json() if resp.status_code == 200 else []
    return render_template("data_parkir.html", parkings=parkings)

@app.route("/force-complete/<int:parking_id>", methods=["PUT"])
def force_complete(parking_id):
    if "admin_email" not in session: return jsonify({"success": False}), 401
    
    admin_user_id = int(session.get("admin_user_id"))
    payload = {"adminUserId": admin_user_id, "parkingId": parking_id}
    
    resp = requests.put(
        f"{API_BASE}/api/parkirAdmin/force-complete/{parking_id}", 
        json=payload
    )
    if resp.status_code == 200:
        return jsonify({"success": True, "message": "Force complete berhasil."})
    return jsonify({"success": False, "message": "Gagal di Backend."}), 400



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=False, threaded=True)