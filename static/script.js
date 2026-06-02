const micBtn = document.getElementById('micBtn');
const waveform = document.getElementById('waveform');
const thinking = document.getElementById('thinking');
const micHint = document.getElementById('micHint');
const chatBox = document.getElementById('chatBox');
const textInput = document.getElementById('textInput');
const sendBtn = document.getElementById('sendBtn');
const clearBtn = document.getElementById('clearBtn');

const chatModeBtn = document.getElementById('chatModeBtn');
const overModeBtn = document.getElementById('overModeBtn');
const chatArea = document.getElementById('chatArea');
const voiceOverArea = document.getElementById('voiceOverArea');
const voiceOverBtn = document.getElementById('voiceOverBtn');
const voiceOverInput = document.getElementById('voiceOverInput');
const dropZone = document.getElementById('dropZone');
const voiceOverHint = document.getElementById('voiceOverHint');
const textRow = document.getElementById('textRow');
const voiceOverText = document.getElementById('voiceOverText');
const transcribeToggle = document.getElementById('transcribeToggle');

let currentMode = 'chat';
let recording = false;
let mediaRecorder = null;
let chunks = [];
let currentAudio = null;
let selectedVoiceOverFile = null;

function ts() {
  return new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.innerText = text;
  return div.innerHTML;
}

function stopCurrentAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
  }
}

function playAudio(audioUrl) {
  stopCurrentAudio();
  currentAudio = new Audio(audioUrl);
  currentAudio.play().catch(err => console.log("Audio play blocked:", err));
}

function addMsg(role, text, audioUrl = null) {
  const label = {user:'YOU', ai:'AI', err:'!!'}[role] || role;
  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const safeText = escapeHtml(text);

  const audioHtml = audioUrl ? `
    <div class="audio-pill" data-audio="${audioUrl}">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      play voice response
    </div>` : '';

  div.innerHTML = `
    <div class="avatar">${label}</div>
    <div class="msg-body">
      <div class="msg-text">${safeText}</div>
      ${audioHtml}
      <div class="msg-time">${ts()}</div>
    </div>`;

  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;

  const audioPill = div.querySelector(".audio-pill");
  if (audioPill) {
    audioPill.addEventListener("click", () => playAudio(audioPill.dataset.audio));
  }
}

function setLoading(on) {
  thinking.classList.toggle('show', on);
  if (on) waveform.classList.remove('show');
  micBtn.disabled = on;
  sendBtn.disabled = on;
  textInput.disabled = on;
  voiceOverBtn.disabled = on;
}

function switchMode(mode) {
  currentMode = mode;

  if (mode === 'chat') {
    chatModeBtn.classList.add('active');
    overModeBtn.classList.remove('active');
    chatArea.classList.remove('hidden');
    voiceOverArea.classList.add('hidden');
    textRow.classList.remove('hidden');
  } else {
    chatModeBtn.classList.remove('active');
    overModeBtn.classList.add('active');
    chatArea.classList.add('hidden');
    voiceOverArea.classList.remove('hidden');
    textRow.classList.add('hidden');
  }
}

async function sendAudio(blob) {
  setLoading(true);

  const form = new FormData();
  form.append('audio', blob, 'user_input.wav');

  try {
    const res = await fetch('/process_audio', {
      method: 'POST',
      body: form
    });

    const data = await res.json();

    if (res.ok) {
      addMsg('user', data.user_text ? `🎤 ${data.user_text}` : '🎤 voice message');
      addMsg('ai', data.response, data.audio_url || null);
      if (data.audio_url) playAudio(data.audio_url);
    } else {
      addMsg('err', '⚠ ' + (data.response || 'Server error'));
    }
  } catch (err) {
    console.error(err);
    addMsg('err', '⚠ Cannot reach Flask server.');
  } finally {
    setLoading(false);
    micHint.textContent = 'tap to speak';
  }
}

async function sendTextMessage() {
  const t = textInput.value.trim();
  if (!t) return;

  addMsg('user', t);
  textInput.value = '';
  setLoading(true);

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: t })
    });

    const data = await res.json();

    if (res.ok) {
      addMsg('ai', data.response, data.audio_url || null);
      if (data.audio_url) playAudio(data.audio_url);
    } else {
      addMsg('err', '⚠ ' + (data.response || 'Server error'));
    }
  } catch (err) {
    console.error(err);
    addMsg('err', '⚠ Cannot reach Flask server.');
  } finally {
    setLoading(false);
  }
}

async function toggleMic() {
  if (!recording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      chunks = [];

      mediaRecorder.ondataavailable = e => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/wav' });
        sendAudio(blob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      recording = true;
      micBtn.classList.add('active');
      waveform.classList.add('show');
      micHint.textContent = 'recording… tap to stop';
    } catch (err) {
      console.error(err);
      alert('Microphone permission denied or unavailable.');
    }
  } else {
    mediaRecorder.stop();
    recording = false;
    micBtn.classList.remove('active');
    waveform.classList.remove('show');
    micHint.textContent = 'processing…';
  }
}

function handleVoiceOverFile(file) {
  selectedVoiceOverFile = file;
  voiceOverHint.textContent = `Selected reference voice: ${file.name}`;
}

async function sendVoiceOver() {
  if (!selectedVoiceOverFile) {
    voiceOverHint.textContent = "Please upload a reference voice file first.";
    return;
  }

  setLoading(true);

  const form = new FormData();
  form.append('reference_wav', selectedVoiceOverFile, selectedVoiceOverFile.name);
  form.append('text_input', voiceOverText.value.trim());
  form.append('use_transcribe', transcribeToggle.checked ? '1' : '0');

  try {
    const res = await fetch('/voice-over', {
      method: 'POST',
      body: form
    });

    const data = await res.json();

    if (res.ok) {
      addMsg('user', `🎬 Reference voice uploaded: ${selectedVoiceOverFile.name}`);
      addMsg('ai', data.source_text ? `📝 Voice over text: ${data.source_text}` : 'Voice over generated', data.audio_url || null);
      if (data.audio_url) playAudio(data.audio_url);

      selectedVoiceOverFile = null;
      voiceOverInput.value = "";
      voiceOverText.value = "";
      voiceOverHint.textContent = "Upload another reference voice or switch back to chat.";
    } else {
      addMsg('err', '⚠ ' + (data.response || 'Server error'));
    }
  } catch (err) {
    console.error(err);
    addMsg('err', '⚠ Cannot reach Flask server.');
  } finally {
    setLoading(false);
  }
}

micBtn.addEventListener('click', toggleMic);
sendBtn.addEventListener('click', sendTextMessage);
textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') sendTextMessage();
});
clearBtn.addEventListener('click', () => {
  chatBox.innerHTML = '';
  stopCurrentAudio();
});

chatModeBtn.addEventListener('click', () => switchMode('chat'));
overModeBtn.addEventListener('click', () => switchMode('over'));

voiceOverBtn.addEventListener('click', sendVoiceOver);

voiceOverInput.addEventListener('change', e => {
  if (e.target.files.length > 0) handleVoiceOverFile(e.target.files[0]);
});

dropZone.addEventListener('click', () => voiceOverInput.click());

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('dragging');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('dragging');
});

dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragging');
  const files = e.dataTransfer.files;
  if (files.length > 0) handleVoiceOverFile(files[0]);
});

setTimeout(() => {
  addMsg('ai', "Hello! Use Voice Chat for conversation, or switch to Voice Over to upload audio.");
}, 600);