import os
from fastapi import FastAPI
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import uvicorn

DT_PLATFORM_TOKEN = os.environ.get("DT_PLATFORM_TOKEN")
DYNA_APP_BASE = os.environ.get("DYNA_APP_BASE", "https://ywo70142.apps.dynatrace.com")

app = FastAPI(title="FactoryGuard Dynatrace Agent")

# Connect to Dynatrace MCP server using your Platform Token
dynatrace_tools = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=f"{DYNA_APP_BASE}/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp",
        headers={"Authorization": f"Bearer {DT_PLATFORM_TOKEN}"},
    )
)

agent = LlmAgent(
    name="factoryguard_dynatrace_agent",
    model="gemini-2.5-flash",
    instruction="""You are FactoryGuard AI, a motor diagnostic engineer.
    Use the Dynatrace tools to fetch current, temperature, vibration, and voltage.
    Compare with thresholds: current <15.2A, temp <80°C, vibration <4.5 mm/s, voltage 380-420V.
    If any exceed, give a root cause and recommended action.""",
    tools=[dynatrace_tools]
)

runner = Runner(agent=agent, session_service=InMemorySessionService())

class AskRequest(BaseModel):
    question: str
    session_id: str = "default"

@app.post("/ask")
async def ask_agent(request: AskRequest):
    response = ""
    async for event in runner.run_async(
        user_id="user",
        session_id=request.session_id,
        new_message=request.question,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response += part.text
    return {"answer": response}

@app.get("/health")
async def health():
    return {"status": "healthy", "dynatrace_mcp": "configured"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
