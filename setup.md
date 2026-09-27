# Run modern-mcp on another system

These steps assume Python 3.14 and uv are already installed. Commands work in
Windows PowerShell and macOS/Linux terminals unless a shell is specified.
Internet access is needed to download dependencies. Run commands from the
repository root; uv creates and manages `.venv` without manual activation.

## 1. Get the project

If Git is installed:

```sh
git clone https://github.com/Utsav-J/mcpmaxxing.git
cd mcpmaxxing
```

Alternatively, download the repository ZIP from GitHub, extract it, and open a
terminal in the extracted folder containing `pyproject.toml` and `uv.lock`.
Use the commit or branch containing the changes you want to run. Local uncommitted
changes are not included in a GitHub clone.

Check the installed tools:

```sh
python --version
uv --version
```

On systems where the Python command is `python3`, use `python3 --version`.

## 2. Install and start the MCP server

```sh
uv sync --frozen --no-dev --python 3.14
uv run --frozen --no-dev modern-mcp --host 127.0.0.1 --port 8000
```

Leave this terminal running. The MCP endpoint is:

```text
http://127.0.0.1:8000/mcp
```

The server uses Streamable HTTP. Configure an MCP client with this URL and that
transport; there is no stdio or standalone SSE mode. Opening the URL in a browser
is not a tool invocation and may return a protocol error.

The server needs no Google API key, external database, or agent process. Its
bookstore fixture and context documents are packaged with the project. The fixture
uses a fixed reference date of 2026-09-26, rather than today's date.

Successful tool results are cached for five minutes in
`artifacts/mcp-cache.sqlite3`. The process needs write access to this location.
Stop the server with Ctrl+C.

## 3. Verify a real MCP call

With the server still running, open another terminal in the repository root and
save the following as `check_mcp.py`:

```python
import asyncio

from mcp import Client


async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        tools = (await client.list_tools()).tools
        print("Tools:", ", ".join(tool.name for tool in tools))
        result = await client.call_tool("get_books", {"limit": 1})
        assert not result.is_error, result.content
        print(result.structured_content)
        print("Cache:", result.meta)


asyncio.run(main())
```

Run it:

```sh
uv run --frozen --no-dev python check_mcp.py
```

Expect seven tool names and one catalog book. Repeat the call within five minutes
to see a cache hit. An earlier matching request may already have populated it.

## 4. Optional: run the Gemini agent

The agent is a separate process that connects to the running MCP server.
Install its dependencies:

```sh
uv sync --frozen --extra agent --no-dev --python 3.14
```

Create a `.env` file in the repository root:

```dotenv
GOOGLE_API_KEY=your_google_api_key
```

Replace the placeholder with your key. `.env` is ignored by Git. Only the agent
reads this file; the MCP server does not need the key.

For direct interactive chat, run in a second terminal:

```sh
uv run --frozen --no-dev --extra agent python -m examples.agent --mcp-url http://127.0.0.1:8000/mcp
```

For a single request:

```sh
uv run --frozen --no-dev --extra agent python -m examples.agent --mcp-url http://127.0.0.1:8000/mcp --query "Show books imported last month from vendor A"
```

To use the A2A interface instead, start the agent service in the second terminal:

```sh
uv run --frozen --no-dev --extra agent python -m examples.agent --serve --mcp-url http://127.0.0.1:8000/mcp --host 127.0.0.1 --port 9999
```

Then start the conversational client in a third terminal:

```sh
uv run --frozen --no-dev --extra agent python -m examples.agent.client --url http://127.0.0.1:9999
```

Try `Show books imported last month from vendor A`, then `Now vendor B`.
Ctrl+C or EOF exits the chat. Conversation history stays in memory; logs and agent
metadata caches are written under `artifacts/agent/`.

The default Gemini model can be overridden with `--model MODEL_NAME` on the agent
command. See [the agent guide](examples/agent/README.md) for details.

## 5. Optional: connect from another computer

For a trusted local network, bind the server to all interfaces and allow its
actual hostname or IP. Replace `192.168.1.50` below with the server's LAN address.

Windows PowerShell:

```powershell
$env:MCP_ALLOWED_HOSTS = "127.0.0.1:*,localhost:*,192.168.1.50:*"
uv run --frozen --no-dev modern-mcp --host 0.0.0.0 --port 8000
```

macOS/Linux:

```sh
export MCP_ALLOWED_HOSTS='127.0.0.1:*,localhost:*,192.168.1.50:*'
uv run --frozen --no-dev modern-mcp --host 0.0.0.0 --port 8000
```

Allow inbound TCP port 8000 through the server's firewall for the intended network.
On the other computer, connect to `http://192.168.1.50:8000/mcp`. You can also pass
that URL to the agent's `--mcp-url` option. `0.0.0.0` is a listening address, not a
client URL.

If a browser-based client sends an Origin header, set `MCP_ALLOWED_ORIGINS` to
its exact origin, such as `http://192.168.1.60:3000`, before starting the server.
The example server has no authentication configured; public hosting requires an
appropriate authentication and HTTPS setup.

## Troubleshooting

- **Python version mismatch:** use Python 3.14 with the `--python 3.14` sync option.
  This project requires Python 3.14 or newer.
- **Connection refused:** keep the server terminal running and check the host and
  port. From another computer, `127.0.0.1` points to that computer, not the server.
- **Port already in use:** start with `--port 8001` and update the client URL to
  `http://127.0.0.1:8001/mcp`.
- **Host/Origin rejected:** configure the actual host or browser origin as shown
  above, then restart the server.
- **Missing agent packages:** use `--extra agent` when both syncing and running
  agent commands.
- **Missing or rejected Google key:** check the root `.env` file and your provider
  access. A key is required only for the Gemini agent.
- **Cache permission error:** choose a writable cache file using `MCP_CACHE_PATH`
  before launching. In PowerShell use `$env:MCP_CACHE_PATH = "C:/path/to/cache.sqlite3"`;
  in macOS/Linux use `export MCP_CACHE_PATH='/path/to/cache.sqlite3'`.

## Optional: run the development checks

These checks use local model doubles and do not require a Google API key:

```sh
uv sync --frozen --extra agent --extra examples --python 3.14
uv run --frozen --extra agent --extra examples python -m pytest -q
uv run --frozen --extra agent --extra examples ruff check src examples scripts tests
```
