let mediaRecorder;
let audioChunks = [];

const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusText = document.getElementById("status");
const orb = document.getElementById("orb");

startBtn.onclick = async () => {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = e => {
            audioChunks.push(e.data);
        };

        mediaRecorder.onstop = sendAudioToServer;

        mediaRecorder.start();
        statusText.innerText = "Recording...";
        console.log("Recording started");

    } catch (err) {
        console.error("Mic error:", err);
    }
};

stopBtn.onclick = () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        statusText.innerText = "Processing...";
        console.log("Recording stopped");
    } else {
        console.log("Recorder not started properly");
    }
};

async function sendAudioToServer() {
    console.log("Sending audio to backend");

    const blob = new Blob(audioChunks, { type: "audio/wav" });
    const formData = new FormData();
    formData.append("audio", blob);

    try {
        const response = await fetch("/process_audio", {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        console.log("Server response:", data);

        statusText.innerText = data.response;

        const audio = new Audio(data.audio_url);

        orb.style.display = "block";
        orb.classList.add("speaking");

        await audio.play();

        audio.onended = () => {
            orb.classList.remove("speaking");
            orb.style.display = "none";
        };

    } catch (err) {
        console.error("Fetch error:", err);
    }
}