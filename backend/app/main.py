from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from services.llm import get_llm

# Create FastAPI app instance
app = FastAPI()

class ChatRequest(BaseModel):
    """
    Request model for chat endpoint.
    """
    message: str

class ChatResponse(BaseModel):
    """
    Response model for chat endpoint.
    """
    response: str

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Receives a user message, sends it to the vLLM API, and returns the response.
    """
    try:
        llm = get_llm()
        # Send the message to the LLM and get the response
        result = llm.invoke(request.message)
        return ChatResponse(response=result.content)
    except Exception as e:
        # Return HTTP 500 if any error occurs
        raise HTTPException(status_code=500, detail=str(e)) 