# Speech-to-Video Orchestrator

This repository serves as the central orchestrator that links together the **PersonaPlex Web App** and the **Live Voice Streaming (Speech-to-Speech)** modules.

## ⚠️ Important Environment Warning

This orchestrator dynamically imports submodules from `personaplex-work` and `speech-to-speech-light`. Because these sub-repositories have fundamentally conflicting dependency constraints (specifically regarding `torch`, `torchaudio`, and `numpy`), **they cannot share a standard unified lockfile.**

If you run a standard `uv sync` inside this orchestrator repository, it will attempt to forcefully resolve the environment, which breaks the C++ ABI linkages for libraries like `torchaudio` and `whisperx` when dynamically imported from other virtual environments.

**DO NOT run `uv sync` in this directory.** 

Instead, we manually infect the orchestrator's virtual environment using `uv pip install` to provide the overlapping heavy dependencies natively, preventing cross-environment import crashes.

---

## 🚀 Setup Instructions (From Scratch)

If you are setting this up on a new machine, or if you accidentally deleted your `.venv` directory, follow these steps strictly in order:

### 1. Sync the Submodules First
Ensure that the two dependent sub-repositories have their environments set up using standard syncing.

```bash
# Setup PersonaPlex Web App
cd ../personaplex-work/web_app
uv sync

# Setup Live Voice Streaming
cd ../../speech-to-speech-light/live-voice-streaming
uv sync
```

### 2. Setup the Orchestrator Environment
Return to this orchestrator directory and create the initial environment using the lockfile. 

```bash
cd /workspace/speech-to-video-orchestrator
uv sync
```

Your environment is now successfully linked and ready to run!

---

## 🏃‍♂️ Running the Orchestrator

Run the application using standard `uv`:

```bash
uv run orchestrator.py
```
