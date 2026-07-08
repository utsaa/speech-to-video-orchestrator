import os
import sys
import asyncio
import numpy as np
import argparse
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
import websockets
from dotenv import load_dotenv
from logger import logger
from core.signals import ClientSignal

load_dotenv()

# Audio Constants
BYTES_PER_SAMPLE = int(os.environ.get("BYTES_PER_SAMPLE", 4))
SAMPLE_RATE = int(os.environ.get("SAMPLE_RATE", 16000))

app = FastAPI()

ORCHESTRATOR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(ORCHESTRATOR_DIR)

VIDEO_MODEL = os.environ.get("VIDEO_MODEL", "ECHOMIMIC_V2").upper()

if VIDEO_MODEL == "ECHOMIMIC_V3":
    S2V_DIR = os.path.join(ROOT_DIR, "echomimic_v3")
    S2V_WEB_APP = os.path.join(S2V_DIR, "web_app")
    S2V_VENV_PYTHON = os.path.join(S2V_DIR, ".venv", "bin", "python")
else:
    S2V_DIR = os.path.join(ROOT_DIR, "personaplex-work")
    S2V_WEB_APP = os.path.join(S2V_DIR, "web_app")
    S2V_VENV_PYTHON = os.path.join(S2V_WEB_APP, ".venv", "bin", "python")

S2V_IPC_SCRIPT = os.path.join(S2V_WEB_APP, "ipc_server.py")

S2S_DIR = os.path.join(ROOT_DIR, "speech-to-speech-light")
S2S_LIVE_DIR = os.path.join(S2S_DIR, "live-voice-streaming")
S2S_VENV_PYTHON = os.path.join(S2S_LIVE_DIR, ".venv", "bin", "python")
S2S_IPC_SCRIPT = os.path.join(S2S_LIVE_DIR, "ipc_server.py")

connected_clients = set()
s2s_process = None
s2v_process = None

s2s_ws_client = None
s2v_ws_client = None

s2s_task = None
s2v_task = None

async def pipe_logs(stream, prefix):
    while True:
        line = await stream.readline()
        if not line:
            break
        decoded = line.decode('utf-8', errors='replace').strip()
        if decoded:
            logger.info(f"[{prefix}] {decoded}")

async def start_subprocess(python_path, script_path, cwd, prefix, *extra_args):
    logger.info(f"🚀 Spawning subprocess for {prefix}...")
    command = [python_path, script_path] + list(extra_args)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={"PYTHONUNBUFFERED": "1", **os.environ},
        start_new_session=True
    )
    asyncio.create_task(pipe_logs(process.stdout, prefix))
    return process

async def bridge_s2s():
    global s2s_ws_client, s2v_ws_client
    uri = os.environ.get("S2S_IPC_URI", "ws://127.0.0.1:8181/ws/ipc")
    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as ws:
                logger.info("✅ Connected to S2S IPC Server")
                s2s_ws_client = ws
                while True:
                    data = await ws.recv()
                    if s2v_ws_client:
                        audio_ms = (len(data) * 1000) / (BYTES_PER_SAMPLE * SAMPLE_RATE)
                        logger.info(f"[ROUTER] Routing TTS audio to S2V ({len(data)} bytes, ~{audio_ms:.0f}ms).")
                        await s2v_ws_client.send(data)
                        await s2v_ws_client.send(ClientSignal.FLUSH_REQUEST.value)
                        logger.info("[ROUTER] Pushed FLUSH_REQUEST sentinel to S2V after sentence chunk.")
        except Exception as e:
            logger.warning(f"S2S IPC disconnected: {e}. Reconnecting in 2s...")
            s2s_ws_client = None
            await asyncio.sleep(2)

async def bridge_s2v():
    global s2v_ws_client
    uri = os.environ.get("S2V_IPC_URI", "ws://127.0.0.1:8182/ws/ipc")
    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as ws:
                logger.info("✅ Connected to S2V IPC Server")
                s2v_ws_client = ws
                while True:
                    data = await ws.recv()
                    if isinstance(data, bytes) and data == b'\x03':
                        logger.info("[ROUTER] Received explicit Flush Signal (Tag 03) from S2V, forwarding to Web UI.")
                    dead = set()
                    for client in list(connected_clients):
                        try:
                            await client.send_bytes(data)
                        except:
                            dead.add(client)
                    for c in dead:
                        connected_clients.remove(c)
        except Exception as e:
            logger.warning(f"S2V IPC disconnected: {e}. Reconnecting in 2s...")
            s2v_ws_client = None
            await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    global s2s_process, s2v_process, s2s_task, s2v_task
    s2s_process = await start_subprocess(S2S_VENV_PYTHON, S2S_IPC_SCRIPT, S2S_LIVE_DIR, "S2S")
    s2v_process = await start_subprocess(S2V_VENV_PYTHON, S2V_IPC_SCRIPT, S2V_WEB_APP, "S2V")
    
    s2s_task = asyncio.create_task(bridge_s2s())
    s2v_task = asyncio.create_task(bridge_s2v())
    
    logger.info("⏳ AI models are loading into VRAM in the background... (This can take 1-2 minutes)")
    logger.info("✅ Orchestrator UI port is opening immediately. AI backends will connect when ready.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down orchestrator and subprocesses...")
    import signal
    if s2s_process:
        try:
            os.killpg(os.getpgid(s2s_process.pid), signal.SIGKILL)
        except Exception as e:
            logger.error(f"Failed to kill S2S process group: {e}")
    if s2v_process:
        try:
            os.killpg(os.getpgid(s2v_process.pid), signal.SIGKILL)
        except Exception as e:
            logger.error(f"Failed to kill S2V process group: {e}")
            
    if s2s_task:
        s2s_task.cancel()
    if s2v_task:
        s2v_task.cancel()

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(ORCHESTRATOR_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
        
    video_w = os.environ.get("VIDEO_WIDTH")
    video_h = os.environ.get("VIDEO_HEIGHT")

    if VIDEO_MODEL == "ECHOMIMIC_V3":
        html = re.sub(r'\{\{\s*VIDEO_W\s*\}\}', video_w if video_w else '384', html)
        html = re.sub(r'\{\{\s*VIDEO_H\s*\}\}', video_h if video_h else '384', html)
        html = re.sub(r'\{\{\s*TARGET_FPS\s*\}\}', '25', html)
    else:
        html = re.sub(r'\{\{\s*VIDEO_W\s*\}\}', video_w if video_w else '512', html)
        html = re.sub(r'\{\{\s*VIDEO_H\s*\}\}', video_h if video_h else '512', html)
        html = re.sub(r'\{\{\s*TARGET_FPS\s*\}\}', '24', html)
        
    return html

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"🌐 [WebSocket] Browser client connected: {websocket.client}")
    
    recording = []
    is_speaking = False
    silence_timer = 0
    vad_threshold = 0.015
    
    try:
        while True:
            message = await websocket.receive()
            if "text" in message:
                text = message["text"]
                if text == ClientSignal.FLUSH_REQUEST.value:
                    logger.info("[WEB] Received manual FLUSH_REQUEST from client.")
                    
                    # Instantly flush any pending VAD mic audio to S2S
                    if is_speaking and len(recording) > 0:
                        logger.info("🛑 [VAD] Manual flush triggered. Queuing to S2S STT instantly.")
                        is_speaking = False
                        audio_data = np.concatenate(recording, axis=0)
                        if s2s_ws_client:
                            logger.info(f"📤 [ROUTER] Pushing {len(audio_data)} total samples to S2S.")
                            await s2s_ws_client.send(audio_data.tobytes())
                        recording = []
                        
                    # Forward flush to S2V
                    if s2v_ws_client:
                        await s2v_ws_client.send(ClientSignal.FLUSH_REQUEST.value)
            elif "bytes" in message:
                data = message["bytes"]
                indata = np.frombuffer(data, dtype=np.float32)
                rms = np.sqrt(np.mean(np.square(indata)))
                
                # Uncomment for VAD debugging:
                # if len(recording) % 10 == 0:
                #     logger.debug(f"[DEBUG] Received audio chunk. len={len(indata)}, rms={rms:.5f}, threshold={vad_threshold}")

                if rms > vad_threshold:
                    if not is_speaking:
                        logger.info(f"\n🎙️ [VAD] Speech detected (RMS: {rms:.5f} > {vad_threshold}). Recording...")
                    is_speaking = True
                    silence_timer = 0
                    recording.append(indata.copy())
                elif is_speaking:
                    recording.append(indata.copy())
                    chunk_duration = len(indata) / 16000.0
                    silence_timer += chunk_duration
                        
                    if silence_timer > 0.8:
                        logger.info("🛑 [VAD] Silence detected (timer > 0.8s). Queuing to S2S STT.")
                        is_speaking = False
                        audio_data = np.concatenate(recording, axis=0)
                        if s2s_ws_client:
                            logger.info(f"📤 [ROUTER] Pushing {len(audio_data)} total samples to S2S.")
                            await s2s_ws_client.send(audio_data.flatten().tobytes())
                        else:
                            logger.error("❌ S2S IPC not connected. Dropping audio.")
                        recording.clear()
    except WebSocketDisconnect:
        logger.info(f"🌐 [WebSocket] Client disconnected: {websocket.client}")
        connected_clients.remove(websocket)
    except Exception as e:
        logger.error(f"❌ [WebSocket] Error: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args, _ = parser.parse_known_args()
    
    logger.info(f"🚀 Starting Orchestrator FastAPI Server on http://localhost:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
