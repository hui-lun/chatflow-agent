import os
from langchain_openai import ChatOpenAI

def get_llm():
    """
    Create and return a ChatOpenAI-compatible LLM instance configured for vLLM.
    Environment variable VLLM_API_BASE must be set via docker-compose.
    """
    # Ensure the environment variable is set
    if "VLLM_API_BASE" not in os.environ:
        raise RuntimeError("Environment variable 'VLLM_API_BASE' is not set.")

    api_base = os.environ["VLLM_API_BASE"]

    return ChatOpenAI(
        model="gemma-3-27b-it",
        openai_api_key="EMPTY",       # Required field for compatibility
        openai_api_base=api_base,
        streaming=True,
        temperature=0.7,
        max_tokens=2000
    )
