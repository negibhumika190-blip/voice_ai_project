from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, abort, send_from_directory
import whisper
from TTS.api import TTS
import uuid
import os
import requests
import sqlite3
import random
import smtplib
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_immediately")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    MAX_CONTENT_LENGTH=25 * 1024 * 1024
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
PRIVATE_OUTPUT_DIR = os.path.join(BASE_DIR, "private_outputs")
VOICE_OVER_UPLOAD_DIR = os.path.join(BASE_DIR, "voice_over_uploads")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(PRIVATE_OUTPUT_DIR, exist_ok=True)
os.makedirs(VOICE_OVER_UPLOAD_DIR, exist_ok=True)

ALLOWED_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "ogg", "flac", "webm"}
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "your_email@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your_app_password")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_over_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_text TEXT NOT NULL,
            reference_filename TEXT,
            processed_filename TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def allowed_audio_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS


def send_otp_email(to_email, otp):
    try:
        subject = "Your Voice AI OTP Code"
        body = f"Your OTP for Voice AI login is: {otp}\n\nThis OTP is valid for 5 minutes."

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False


print("Loading Whisper model...")
whisper_model = whisper.load_model("base")

print("Loading TTS model...")
tts = TTS(
    model_name="tts_models/multilingual/multi-dataset/your_tts",
    progress_bar=False
)


def ask_ollama(user_text):
    system_prompt = """
You are a helpful AI assistant.
Answer directly and naturally.
Keep it short unless more detail is needed.
Do not refuse normal questions.
"""
    payload = {
        "model": "tinyllama",
        "prompt": f"{system_prompt}\n\nUser: {user_text}\nAssistant:",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 120
        }
    }

    response = requests.post(
        "http://localhost:11434/api/generate",
        json=payload,
        timeout=120
    )
    response.raise_for_status()
    data = response.json()
    ai_text = data.get("response", "").strip()
    return ai_text if ai_text else "Sorry, I couldn't generate a proper response."


def save_conversation(user_id, role, message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conversations (user_id, role, message, created_at) VALUES (?, ?, ?, ?)",
        (user_id, role, message, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_user_conversations(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, message, created_at FROM conversations WHERE user_id = ? ORDER BY id ASC",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def generate_voice(text_to_speak, user_id, reference_wav="voice_sample.wav"):
    user_folder = os.path.join(PRIVATE_OUTPUT_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)

    output_filename = f"voice_{uuid.uuid4().hex}.wav"
    output_path = os.path.join(user_folder, output_filename)

    tts.tts_to_file(
        text=text_to_speak,
        speaker_wav=reference_wav,
        language="en",
        file_path=output_path
    )
    return output_filename


def save_voice_over_job(user_id, source_type, source_text, reference_filename, processed_filename):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO voice_over_jobs (user_id, source_type, source_text, reference_filename, processed_filename, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, source_type, source_text, reference_filename, processed_filename, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed_password)
            )
            conn.commit()
            conn.close()

            flash("Signup successful! Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already exists.", "error")
            return redirect(url_for("signup"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["email"] = email
            return redirect(url_for("index"))

        flash("Invalid email or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/send_otp", methods=["POST"])
def send_otp():
    email = request.form.get("email", "").strip().lower()

    if not email:
        flash("Please enter your email first.", "error")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    conn.close()

    if not user:
        flash("No account found with this email.", "error")
        return redirect(url_for("login"))

    otp = str(random.randint(100000, 999999))
    session["otp"] = otp
    session["otp_email"] = email
    session["otp_user_id"] = user["id"]
    session["otp_username"] = user["username"]
    session["otp_expires_at"] = (datetime.utcnow() + timedelta(minutes=5)).isoformat()

    sent = send_otp_email(email, otp)

    if sent:
        flash("OTP sent to your email.", "success")
    else:
        flash("Failed to send OTP. Check email settings in app.py", "error")

    return redirect(url_for("login"))


@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    entered_otp = request.form.get("otp", "").strip()

    if "otp" not in session:
        flash("Please request OTP first.", "error")
        return redirect(url_for("login"))

    expires_at = session.get("otp_expires_at")
    if expires_at and datetime.utcnow() > datetime.fromisoformat(expires_at):
        session.clear()
        flash("OTP expired. Please request a new one.", "error")
        return redirect(url_for("login"))

    if entered_otp == session.get("otp"):
        session["user_id"] = session.get("otp_user_id")
        session["username"] = session.get("otp_username")
        session["email"] = session.get("otp_email")

        session.pop("otp", None)
        session.pop("otp_email", None)
        session.pop("otp_user_id", None)
        session.pop("otp_username", None)
        session.pop("otp_expires_at", None)

        flash("Logged in successfully with OTP.", "success")
        return redirect(url_for("index"))

    flash("Invalid OTP.", "error")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    conversations = get_user_conversations(session["user_id"])
    return render_template(
        "index.html",
        username=session.get("username", "User"),
        conversations=conversations
    )


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    try:
        data = request.get_json() or {}
        user_text = data.get("message", "").strip()

        if not user_text:
            return jsonify({"response": "Please type something."}), 400

        save_conversation(session["user_id"], "user", user_text)
        ai_text = ask_ollama(user_text)
        save_conversation(session["user_id"], "ai", ai_text)

        audio_filename = generate_voice(ai_text, session["user_id"], "voice_sample.wav")

        return jsonify({
            "response": ai_text,
            "audio_url": url_for("get_private_audio", user_id=session["user_id"], filename=audio_filename)
        })

    except requests.exceptions.ConnectionError:
        return jsonify({"response": "Ollama is not running. Start it first."}), 500
    except Exception as e:
        print("TEXT CHAT ERROR:", str(e))
        return jsonify({"response": "Backend error occurred", "error": str(e)}), 500


@app.route("/process_audio", methods=["POST"])
@login_required
def process_audio():
    try:
        if "audio" not in request.files:
            return jsonify({"response": "No audio file received"}), 400

        audio_file = request.files["audio"]
        input_path = os.path.join(TEMP_DIR, f"user_input_{uuid.uuid4().hex}.wav")
        audio_file.save(input_path)

        result = whisper_model.transcribe(input_path)
        user_text = result["text"].strip()

        if not user_text:
            if os.path.exists(input_path):
                os.remove(input_path)
            return jsonify({"response": "No speech detected"}), 400

        save_conversation(session["user_id"], "user", user_text)
        ai_text = ask_ollama(user_text)
        save_conversation(session["user_id"], "ai", ai_text)

        audio_filename = generate_voice(ai_text, session["user_id"], "voice_sample.wav")

        if os.path.exists(input_path):
            os.remove(input_path)

        return jsonify({
            "user_text": user_text,
            "response": ai_text,
            "audio_url": url_for("get_private_audio", user_id=session["user_id"], filename=audio_filename)
        })

    except requests.exceptions.ConnectionError:
        return jsonify({"response": "Ollama is not running. Start it first."}), 500
    except Exception as e:
        print("ERROR OCCURRED:", str(e))
        return jsonify({"response": "Backend error occurred", "error": str(e)}), 500


@app.route("/voice-over", methods=["POST"])
@login_required
def voice_over():
    try:
        reference_wav = request.files.get("reference_wav")
        text_input = request.form.get("text_input", "").strip()
        use_transcribe = request.form.get("use_transcribe", "1").strip() == "1"

        if not reference_wav or reference_wav.filename == "":
            return jsonify({"response": "Reference voice file is required"}), 400

        if not allowed_audio_file(reference_wav.filename):
            return jsonify({"response": "Unsupported reference audio format"}), 400

        reference_name = secure_filename(reference_wav.filename)
        reference_path = os.path.join(VOICE_OVER_UPLOAD_DIR, f"ref_{uuid.uuid4().hex}_{reference_name}")
        reference_wav.save(reference_path)

        print("REFERENCE PATH:", reference_path)
        print("EXISTS:", os.path.exists(reference_path))
        print("TEXT INPUT:", text_input)
        print("TRANSCRIBE:", use_transcribe)

        final_text = text_input

        if not final_text and use_transcribe:
            result = whisper_model.transcribe(reference_path)
            final_text = result["text"].strip()

        if not final_text:
            if os.path.exists(reference_path):
                os.remove(reference_path)
            return jsonify({"response": "Please provide text or upload clear audio for transcription"}), 400

        output_filename = generate_voice(final_text, session["user_id"], reference_path)
        save_voice_over_job(
            session["user_id"],
            "text" if text_input else "transcribed_audio",
            final_text,
            reference_name,
            output_filename
        )

        if os.path.exists(reference_path):
            os.remove(reference_path)

        return jsonify({
            "source_text": final_text,
            "response": "Voice over generated successfully.",
            "audio_url": url_for("get_private_audio", user_id=session["user_id"], filename=output_filename)
        })

    except requests.exceptions.ConnectionError:
        return jsonify({"response": "Backend model not running."}), 500
    except Exception as e:
        print("VOICE OVER ERROR:", repr(e))
        return jsonify({"response": "Backend error occurred", "error": str(e)}), 500


@app.route("/audio/<int:user_id>/<filename>")
@login_required
def get_private_audio(user_id, filename):
    if session.get("user_id") != user_id:
        abort(403)

    user_folder = os.path.join(PRIVATE_OUTPUT_DIR, str(user_id))
    return send_from_directory(user_folder, filename, as_attachment=False)


if __name__ == "__main__":
    app.run(debug=True)