from flask import Flask, render_template, request, jsonify
import whisper
from TTS.api import TTS
import uuid
import os
import requests

app = Flask(__name__)

# -------------------------------
# Load Models (Startup pe load honge)
# -------------------------------

print("Loading Whisper model...")
whisper_model = whisper.load_model("base")

print("Loading TTS model...")
tts = TTS(
    model_name="tts_models/multilingual/multi-dataset/your_tts",
    progress_bar=False
)

# -------------------------------
# Routes
# -------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process_audio", methods=["POST"])
def process_audio():
    try:
        print("Audio received")

        if "audio" not in request.files:
            return jsonify({"response": "No audio file received"}), 400

        audio_file = request.files["audio"]
        input_path = "user_input.wav"
        audio_file.save(input_path)

        print("Transcribing...")
        result = whisper_model.transcribe(input_path)
        user_text = result["text"]

        print("User said:", user_text)

        if not user_text.strip():
            return jsonify({"response": "No speech detected"}), 400

        # -------------------------------
        # OLLAMA AI CALL (tinyllama)
        # -------------------------------

        print("Calling Ollama...")

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "tinyllama",
                "prompt": f"Reply in one short sentence only.\n\nUser: {user_text}",
                "stream": False
            }
        )

        ai_text = response.json()["response"].strip()

        print("AI response:", ai_text)

        # -------------------------------
        # Generate Voice
        # -------------------------------

        output_filename = f"output_{uuid.uuid4().hex}.wav"
        output_path = os.path.join("static", output_filename)

        print("Generating voice...")
        tts.tts_to_file(
            text=ai_text,
            speaker_wav="voice_sample.wav",  # tumhari cloned voice file
            language="en",
            file_path=output_path
        )

        print("Voice generated successfully")

        return jsonify({
            "response": ai_text,
            "audio_url": f"/static/{output_filename}"
        })

    except Exception as e:
        print("ERROR OCCURRED:", str(e))
        return jsonify({
            "response": "Backend error occurred",
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True)