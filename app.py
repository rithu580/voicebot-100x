# app.py
import streamlit as st
import requests
import os
import json
from typing import List

st.set_page_config(page_title="Voice Interview Bot — Streamlit", layout="centered")

st.title("Voice Interview Bot (for 100x Stage 1)")
st.markdown(
    """
This demo uses your **persona summary** to answer interview questions in a voice-like style.
- Click **Start recording** and ask a question out loud.
- The browser transcribes (Web Speech API) and sends text to this app.
- The app calls OpenAI's Chat API (backend) and returns a text reply.
- The browser will speak the reply using built-in Text-to-Speech.
"""
)

# --- Persona section (the bot should answer as YOU) ---
st.sidebar.header("Bot persona (edit to make answers sound like you)")
persona = st.sidebar.text_area(
    "Write a short summary of how you'd answer interview questions (1-5 sentences). Example: 'I'm Raghul — full-stack dev, curious, like clear steps, friendly tone.'",
    value="I am Raghul Dominick. I'm a pragmatic problem-solver who likes clear explanations, short examples, and a friendly tone. Keep answers concise and confident."
)

st.sidebar.markdown("**Other settings**")
model = st.sidebar.selectbox("Model (backend)", options=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"], index=2)

# --- API key retrieval (from Streamlit secrets or env) ---
OPENAI_API_KEY = None
if "OPENAI_API_KEY" in st.secrets:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
elif os.getenv("OPENAI_API_KEY"):
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    st.warning(
        "No OPENAI_API_KEY found. For the deployed demo, set OPENAI_API_KEY in Streamlit secrets or the host environment. "
        "Locally you can set environment variable OPENAI_API_KEY."
    )

# --- Chat history display ---
if "history" not in st.session_state:
    st.session_state.history = []

def call_openai_chat(user_text: str, persona_text: str, model_name: str = "gpt-3.5-turbo") -> str:
    """
    Simple wrapper to call OpenAI Chat API via REST.
    Uses OPENAI_API_KEY from environment/secrets.
    """
    if not OPENAI_API_KEY:
        return "Error: OPENAI_API_KEY not configured on the server."

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are an interview voicebot. Answer the user's spoken interview question as if you are the candidate. "
        "Use the persona below to shape tone and content. Keep answers clear and friendly; when asked for lists use numbered points."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Persona summary: {persona_text}"},
        {"role": "user", "content": user_text}
    ]

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.7
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        return f"OpenAI API error {resp.status_code}: {resp.text}"
    data = resp.json()
    # support both streaming and single response shapes; here assume usual completions
    content = data["choices"][0]["message"]["content"]
    return content

# --- UI area for voice controls & transcript ---
st.subheader("Record & ask (browser will transcribe)")
placeholder = st.empty()

# We embed a small HTML/JS component that uses Web Speech API to transcribe and then send the text back to Streamlit.
# The JS will call Streamlit.setComponentValue by posting to the window.parent via Streamlit's postMessage.
recording_component = """
<div>
  <p><b>Instructions:</b> Click Start, speak your question, then click Stop. The browser will transcribe and send the text to the app.</p>
  <button id="start">Start recording</button>
  <button id="stop" disabled>Stop</button>
  <p><i>Transcription:</i></p>
  <div id="transcript" style="min-height:40px;border:1px solid #ddd;padding:8px;"></div>
</div>
<script>
const startBtn = document.getElementById('start');
const stopBtn = document.getElementById('stop');
const transcriptDiv = document.getElementById('transcript');
let recognition;
if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
  transcriptDiv.innerText = 'Speech recognition not supported in this browser. Use Chrome or Edge on desktop/mobile or test locally on https.';
} else {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.lang = 'en-IN';
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.onresult = (event) => {
    let interim = '';
    let final = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const res = event.results[i];
      if (res.isFinal) final += res[0].transcript;
      else interim += res[0].transcript;
    }
    transcriptDiv.innerText = final + interim;
  };

  recognition.onend = () => {
    stopBtn.disabled = true;
    startBtn.disabled = false;
    // send final transcript back to Streamlit via postMessage
    const finalText = transcriptDiv.innerText;
    const payload = {type: 'transcript', text: finalText};
    window.parent.postMessage({isStreamlitMessage: true, scope: 'streamlit:customComponent', args: payload}, '*');
  };

  startBtn.onclick = () => {
    recognition.start();
    startBtn.disabled = true;
    stopBtn.disabled = false;
    transcriptDiv.innerText = '';
  };
  stopBtn.onclick = () => {
    recognition.stop();
  };
}
</script>
"""

# Render the HTML component
transcript_data = st.components.v1.html(recording_component, height=240)

# The JS will post a message; Streamlit can't directly receive it except via components return.
# Workaround: use a small polling keyboard input — below we provide a manual fallback.
st.write("If your browser cannot use voice, type your question here:")
typed = st.text_input("Or paste the transcription here", key="typed_input")

# Send button
if st.button("Send to bot"):
    question = st.session_state.get("typed_input", "").strip()
    if not question:
        st.warning("Please type your question or use the Start Recording button to transcribe.")
    else:
        st.session_state.history.append({"role": "user", "text": question})
        with st.spinner("Getting reply..."):
            reply = call_openai_chat(question, persona, model_name=model)
        st.session_state.history.append({"role": "bot", "text": reply})
        st.success("Reply received — playing TTS in your browser (if supported).")
        # display
        st.markdown("**Bot reply:**")
        st.write(reply)
        # send reply to browser for TTS using JS
        tts_script = f"""
        <script>
          const utter = new SpeechSynthesisUtterance({json.dumps(reply)});
          utter.lang = 'en-US';
          utter.rate = 1.0;
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utter);
        </script>
        """
        st.components.v1.html(tts_script, height=0)

# Show history
st.markdown("---")
st.subheader("Conversation history")
for i, m in enumerate(st.session_state.history[::-1]):
    role = m["role"]
    txt = m["text"]
    if role == "user":
        st.markdown(f"**You:** {txt}")
    else:
        st.markdown(f"**Bot:** {txt}")

st.markdown("---")
st.markdown("**Deployment notes**: Set the `OPENAI_API_KEY` in Streamlit Secrets (or the environment). The browser must have microphone permission and run on HTTPS for Web Speech API to work reliably.")
