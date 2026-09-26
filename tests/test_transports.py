import asyncio
import os
import socket
import subprocess
import sys

import pytest
from mcp import Client

from modern_mcp.registry import ToolContextRegistry

pytestmark = pytest.mark.anyio


async def test_loopback_streamable_http(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "modern_mcp", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            with socket.socket() as connection:
                connection.settimeout(0.05)
                if connection.connect_ex(("127.0.0.1", port)) == 0:
                    break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("Local HTTP server did not become ready.")
        async with Client(f"http://127.0.0.1:{port}/mcp", read_timeout_seconds=5) as client:
            registry = ToolContextRegistry(client, "http-test")
            await registry.refresh()
            assert len(registry.records) == 7
            prepared = await registry.hydrate(["compare_vendors"])
            result = await registry.invoke(
                prepared, "compare_vendors", {"vendor_ids": ["VENDOR-A", "VENDOR-D"]}
            )
            assert len(result["data"]["items"]) == 2
            policies = await registry.synthesis_request(
                "Compare supply", {"compare_vendors": result}, prepared.snapshot
            )
            assert len(policies["presentation_policies"]) == 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()
