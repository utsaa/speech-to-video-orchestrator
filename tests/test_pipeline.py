import sys
import os
import queue
import unittest
import numpy as np
import threading
import time

# ---------------------------------------------------------------------------
# Path Injections for Independent Repos
# ---------------------------------------------------------------------------
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ORCHESTRATOR_DIR = os.path.dirname(TESTS_DIR)
ROOT_DIR = os.path.dirname(ORCHESTRATOR_DIR)

PERSONAPLEX_DIR = os.path.join(ROOT_DIR, "personaplex")
PERSONAPLEX_WEB_APP = os.path.join(PERSONAPLEX_DIR, "web_app")
PERSONAPLEX_ECHOMIMIC = os.path.join(PERSONAPLEX_DIR, "echomimic_v2")

S2S_DIR = os.path.join(ROOT_DIR, "speech-to-speech-light")
S2S_LIVE_DIR = os.path.join(S2S_DIR, "live-voice-streaming")

if PERSONAPLEX_WEB_APP not in sys.path:
    sys.path.insert(0, PERSONAPLEX_WEB_APP)
if PERSONAPLEX_ECHOMIMIC not in sys.path:
    sys.path.insert(0, PERSONAPLEX_ECHOMIMIC)
if S2S_LIVE_DIR not in sys.path:
    sys.path.insert(0, S2S_LIVE_DIR)

# S2V Imports
from core.signals import ClientSignal

class TestPipelineFlow(unittest.TestCase):

    def test_audio_routing_format(self):
        """
        Verify that dummy audio chunks can be successfully placed into S2V input queue
        in the expected float32 format.
        """
        s2v_input_queue = queue.Queue()
        
        # S2S outputs np.float32 audio chunks
        dummy_audio = np.random.rand(16000).astype(np.float32)
        
        try:
            s2v_input_queue.put_nowait(dummy_audio)
        except queue.Full:
            self.fail("Queue was unexpectedly full.")
            
        retrieved_audio = s2v_input_queue.get_nowait()
        
        self.assertEqual(retrieved_audio.dtype, np.float32, "Audio should be float32")
        self.assertEqual(len(retrieved_audio), 16000, "Audio length mismatch")
        
    def test_s2v_client_signal_routing(self):
        """
        Verify that manual flush signals can be routed correctly to the S2V input queue.
        """
        s2v_input_queue = queue.Queue()
        
        try:
            s2v_input_queue.put_nowait(ClientSignal.FLUSH_REQUEST)
        except queue.Full:
            self.fail("Queue was unexpectedly full.")
            
        signal = s2v_input_queue.get_nowait()
        self.assertIsInstance(signal, ClientSignal, "Expected a ClientSignal enum")
        self.assertEqual(signal, ClientSignal.FLUSH_REQUEST, "Expected FLUSH_REQUEST")

    def test_s2v_output_routing(self):
        """
        Verify that dummy frames and audio can be retrieved from S2V output queues.
        """
        s2v_frame_queue = queue.Queue()
        s2v_audio_out_queue = queue.Queue()
        
        dummy_frame = b"fake_jpeg_bytes"
        dummy_audio = b"fake_pcm_bytes"
        
        s2v_frame_queue.put_nowait(dummy_frame)
        s2v_audio_out_queue.put_nowait(dummy_audio)
        
        self.assertEqual(s2v_frame_queue.get_nowait(), b"fake_jpeg_bytes")
        self.assertEqual(s2v_audio_out_queue.get_nowait(), b"fake_pcm_bytes")

if __name__ == "__main__":
    unittest.main()
