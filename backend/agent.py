"""Tool-calling agent (LangChain 1.x) com llama3 via Ollama."""

import os

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from prompts import SYSTEM_AGENT
from tools import TOOLS

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

_llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0.3,
)

executor = create_agent(
    model=_llm,
    tools=TOOLS,
    system_prompt=SYSTEM_AGENT,
)
