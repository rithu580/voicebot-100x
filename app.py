import os
import tempfile
import queue
import requests
import json
import numpy as np
import soundfile as sf
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase

st.set_page_config(page_title="Voice Interview Bot — Streamlit (webrtc)", layout="centered")
st.title("Voice Interview Bot — Reliable Server-side Recorder")

st.markdown(
    """
This app uses **WebRTC for recording** + **Whisper speech-to-text** + **Chat API**  
• Click **Start** → speak  
• Click **Stop**  
• Then click **Transcribe latest recording**
"""
)

# -----------------------
# Persona Settings
# -----------------------
st.sidebar.header("Bot Persona")
persona = st.sidebar.text_area(
    "Persona:",
    value="I am Raghul Dominick. I answer questions clearly, confidently, and in a friendly tone."
)

model = st.sidebar.selectbox(
    "Model:",
    ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"], index=2
)

# -----------------------
# API Key
# -----------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)
if not OPENAI_API_KEY:
    st.warning("Missing OPENAI_API_KEY. Set it in environment or Streamlit Secrets.")

# -----------------------
# Audio Processor
# -----------------------
audio_queue = queue.Queue()

class AudioProcessor(AudioProcessorBase):
    def __init__(self):
        self.frames = []
        self.sample_rate = 48000

    def recv(self, frame):
        arr = frame.to_ndarray()
        if arr.dtype != np.float32:
            arr = arr.astype(np.float32) / np.iinfo(arr.dtype).max
        self.frames.append(arr)
        return frame

    def export_wav(self):
        if not self.frames:
            return None

        audio = np.concatenate(self.frames, axis=0)
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)  # convert stereo → mono

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(tmp.name, audio, self.sample_rate)
        tmp.close()
        self.frames = []
        audio_queue.put(tmp.name)
        return tmp.name

# -----------------------
# WebRTC Widget
# -----------------------
st.subheader("🎤 Record Audio")
webrtc_ctx = webrtc_streamer(
    key="voice-recorder",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
)

# -----------------------
# Transcription
# -----------------------
if st.button("Transcribe latest recording"):
    if not webrtc_ctx or not webrtc_ctx.audio_processor:
        st.error("Start the recorder and allow mic permission.")
    else:
        filename = webrtc_ctx.audio_processor.export_wav()
        if not filename:
            st.error("No audio found. Try recording again.")
        else:
            st.success(f"Saved: {filename}")
            st.audio(filename)

            if OPENAI_API_KEY:
                st.info("Transcribing...")

                with open(filename, "rb") as f:
                    resp = requests.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                        data={"model": "whisper-1"},
                        files={"file": f},
                    )

                if resp.status_code == 200:
                    text = resp.json()["text"]
                    st.success("Transcription:")
                    st.write(text)

                    # Chat API
                    st.info("Getting bot reply...")

                    system_prompt = (
                        "You are an interview candidate. "
                        "Answer clearly and professionally using the persona."
                    )

                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "system", "content": f"Persona: {persona}"},
                        {"role": "user", "content": text},
                    ]

                    reply = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages},
                    ).json()["choices"][0]["message"]["content"]

                    st.subheader("🤖 Bot Reply")
                    st.write(reply)

                    st.components.v1.html(
                        f"""
                        <script>
                        var u = new SpeechSynthesisUtterance({json.dumps(reply)});
                        speechSynthesis.speak(u);
                        </script>
                        """,
                        height=0,
                    )

                else:
                    st.error(resp.text)
            else:
                st.error("Missing key.")

# -----------------------
# History
# -----------------------
st.markdown("---")
