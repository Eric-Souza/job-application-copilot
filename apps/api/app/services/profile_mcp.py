"""Read the resume from the profile MCP server instead of local files (optional).

PROFILE_MCP is either a command that starts the server over stdio
("node ../profile-mcp-server/dist/index.js") or the URL of one served over
Streamable HTTP ("http://localhost:3000/mcp"). The server builds the resume from
a structured experience file plus live GitHub and Medium data, in the Markdown
format the indexer expects, and exposes it as the resource profile://resume.
"""

import os
import shlex
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextResourceContents

RESUME_URI = "profile://resume"
# The indexed source's name, as if it were a file in data/resume/
SOURCE_NAME = "profile-mcp-resume.md"


@asynccontextmanager
async def _session(target: str):
    if target.startswith(("http://", "https://")):
        async with streamable_http_client(target) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            yield session
        return
    command, *args = shlex.split(target, posix=os.name != "nt")
    # The server reads GITHUB_TOKEN and friends from the environment, so pass it through
    params = StdioServerParameters(command=command, args=args, env=dict(os.environ))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


async def read_resume(target: str) -> str:
    async with _session(target) as session:
        result = await session.read_resource(RESUME_URI)
    text = "\n".join(c.text for c in result.contents if isinstance(c, TextResourceContents)).strip()
    if not text:
        raise ValueError(f"The profile MCP server returned an empty resume ({target})")
    return text
