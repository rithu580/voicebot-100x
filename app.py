import streamlit as st
import requests
import os
import json
import tempfile

st.set_page_config(page_title="Voice Interview Bot — Stable Version", layout="centered")

st.title("Voice Interview Bot — Stable Recorder (No WebRTC)")
st.write(
    """
This version works on **Streamlit Cloud** without WebRTC.  
Steps:  
1. Click **Record audio**  
2. Speak  
3. Stop  
4. Click **Transcribe & Ask**  
    """
)

# ---------------------------
# Persona
# ---------------------------
persona = st.sidebar.text_area(
    "Your persona:",
    value="I am Raghul Dominick. I answer clearly, confidently, and politely."
)
model = st.sidebar.selectbox("Model", ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"], index=2)

# ---------------------------
# API key
# ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)
if not OPENAI_API_KEY:
    st.warning("OPENAI_API_KEY missing. Set it in Streamlit Secrets.")
    st.stop()

# ---------------------------
# Audio Recorder
# ---------------------------
audio = st.audio_input("Record audio")

if audio is not None:
    st.success("Audio recorded!")

    # Save temp wav file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio.read())
        audio_path = tmp.name

    st.audio(audio_path)

    if st.button("Transcribe & Ask"):
        st.info("Transcribing audio...")
        with open(audio_path, "rb") as f:
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                data={"model": "whisper-1"},
                files={"file": f},
            )

        if resp.status_code != 200:
            st.error(resp.text)
            st.stop()

        text = resp.json()["text"]
        st.success("Transcription:")
        st.write(text)

        # Chat API
        st.info("Generating reply...")
        chat_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an interview assistant."},
                {"role": "system", "content": f"Persona: {persona}"},
                {"role": "user", "content": text},
            ]
        }

        reply = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=chat_payload,
        ).json()["choices"][0]["message"]["content"]

        st.subheader("Bot Reply")
        st.write(reply)

        # TTS
        st.components.v1.html(
            f"""
            <script>
            var u = new SpeechSynthesisUtterance({json.dumps(reply)});
            speechSynthesis.speak(u);
            </script>
            """,
            height=0,
        )
