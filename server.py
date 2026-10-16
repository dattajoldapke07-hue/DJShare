import os
import secrets
import string
import time
import threading
from io import BytesIO
from flask import (
    Flask, request, jsonify,
    send_file, abort, render_template_string
)
from werkzeug.utils import secure_filename

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

# Temporary storage for demo purposes.
sessions = {}
lock = threading.Lock()
SESSION_LIFETIME = 600

PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DJShare</title>
<style>
body {
    background:#050807;color:#00ff88;
    font-family:monospace;text-align:center;padding:25px;
}
.box {
    max-width:420px;margin:35px auto;padding:24px;
    border:1px solid #00ff88;border-radius:12px;
    background:#09110e;
}
input,button {
    box-sizing:border-box;width:100%;padding:13px;
    margin:10px 0;background:#050807;color:#00ff88;
    border:1px solid #00ff88;border-radius:6px;
}
button {background:#00ff88;color:#001b0e;font-weight:bold}
</style>
</head>
<body>
<div class="box">
<h1>DJ<span style="color:white">SHARE</span></h1>
<p>SECURE FILE TRANSFER</p>
<h3>Receive Files</h3>
<form action="/receive" method="get">
<input name="code" placeholder="Enter code e.g. DJ729"
required maxlength="5">
<button>CONNECT</button>
</form>
<p id="status">SHARE ANYTHING. ANYWHERE.</p>
</div>
</body>
</html>
"""

def cleanup():
    now = time.time()
    with lock:
        expired = [
            code for code, data in sessions.items()
            if now - data["created"] > SESSION_LIFETIME
        ]
        for code in expired:
            del sessions[code]

def make_code():
    alphabet = string.digits
    with lock:
        for _ in range(100):
            code = "DJ" + "".join(
                secrets.choice(alphabet) for _ in range(3)
            )
            if code not in sessions:
                return code
    raise RuntimeError("Could not create code")

@app.get("/")
def home():
    return render_template_string(PAGE)

@app.get("/health")
def health():
    return jsonify({"app": "DJShare", "status": "online"})

@app.post("/api/send")
def send():
    cleanup()

    if "files" not in request.files:
        return jsonify({"error": "Select files first"}), 400

    uploaded = request.files.getlist("files")
    saved = []

    for file in uploaded:
        if not file.filename:
            continue

        name = secure_filename(file.filename)
        content = file.read()

        if not name:
            continue

        saved.append({
            "name": name,
            "content": content
        })

    if not saved:
        return jsonify({"error": "No valid files"}), 400

    code = make_code()

    with lock:
        sessions[code] = {
            "created": time.time(),
            "files": saved
        }

    return jsonify({
        "code": code,
        "link": request.host_url + "receive?code=" + code,
        "expires_in_seconds": SESSION_LIFETIME
    })

@app.get("/receive")
def receive():
    cleanup()
    code = request.args.get("code", "").upper()

    with lock:
        data = sessions.get(code)

    if not data:
        abort(404, "Invalid or expired DJShare code")

    files = data["files"]

    links = "".join(
        '<p><a style="color:#00ff88" href="/download/'
        + code + '/' + str(i) + '">'
        + file["name"] + ' — Download</a></p>'
        for i, file in enumerate(files)
    )

    return render_template_string("""
    <body style="background:#050807;color:#00ff88;
    font-family:monospace;text-align:center;padding:25px">
    <h1>DJSHARE</h1>
    <h3>Files ready</h3>
    {{ links|safe }}
    <p>Links expire after 10 minutes.</p>
    </body>
    """, links=links)

@app.get("/download/<code>/<int:index>")
def download(code, index):
    cleanup()

    with lock:
        data = sessions.get(code.upper())
        if not data or index >= len(data["files"]):
            abort(404)

        file = data["files"][index]

        return send_file(
            BytesIO(file["content"]),
            as_attachment=True,
            download_name=file["name"],
            mimetype="application/octet-stream"
        )

@app.errorhandler(413)
def too_large(error):
    return jsonify({"error": "Total upload limit exceeded"}), 413

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
