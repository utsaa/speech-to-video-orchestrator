import pytest
import asyncio
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock

import orchestrator

@pytest.fixture
def mock_subprocesses():
    with patch("orchestrator.start_subprocess", new_callable=AsyncMock) as mock_start:
        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_start.return_value = mock_process
        yield mock_start

@pytest.mark.asyncio
async def test_bridge_routing_logic(mock_subprocesses):
    """
    Verifies that the orchestrator tries to connect to the right S2S and S2V WebSockets
    and doesn't crash on connection failures.
    """
    with patch("orchestrator.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_ws = AsyncMock()
        # Make recv() raise an exception immediately so the loop falls through
        mock_ws.recv.side_effect = Exception("Test Disconnect")
        mock_connect.return_value.__aenter__.return_value = mock_ws
        
        task = asyncio.create_task(orchestrator.bridge_s2s())
        await asyncio.sleep(0.1)
        task.cancel()
        
        mock_connect.assert_called_with("ws://127.0.0.1:8081/ws/ipc", ping_interval=None)

@pytest.mark.asyncio
async def test_vad_triggers_routing(mock_subprocesses):
    """
    Verifies that audio from the browser triggers VAD and successfully routes to S2S.
    """
    from fastapi.websockets import WebSocket
    
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.client = "test_client"
    
    # Simulate receiving loud audio (trigger VAD), then silent audio (flush VAD)
    loud = (np.ones(16000, dtype=np.float32) * 0.5).tobytes()
    silent = np.zeros(16000, dtype=np.float32).tobytes()
    
    mock_ws.receive.side_effect = [
        {"bytes": loud},
        {"bytes": silent},
        Exception("Client Disconnect") # Force exit loop
    ]
    
    # Mock the internal S2S client connection
    orchestrator.s2s_ws_client = AsyncMock()
    
    await orchestrator.websocket_endpoint(mock_ws)
    
    # Assert that the loud audio + silence caused a send to S2S
    orchestrator.s2s_ws_client.send.assert_called()

@pytest.mark.asyncio
async def test_manual_flush(mock_subprocesses):
    """
    Verifies that a manual FLUSH_REQUEST from the browser is routed to S2V.
    """
    from fastapi.websockets import WebSocket
    
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.client = "test_client"
    
    mock_ws.receive.side_effect = [
        {"text": "FLUSH_REQUEST"},
        Exception("Client Disconnect")
    ]
    
    orchestrator.s2v_ws_client = AsyncMock()
    
    await orchestrator.websocket_endpoint(mock_ws)
    
    # Assert FLUSH_REQUEST is routed to S2V
    orchestrator.s2v_ws_client.send.assert_called_with("FLUSH_REQUEST")
