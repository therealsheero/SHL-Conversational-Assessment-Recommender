import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import ChatRequest, ChatResponse, HealthResponse
from app.agent import handle_chat
from app.retriever import get_retriever

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[App] Starting up - loading catalog and building index...")
    start = time.time()
    try:
        retriever = get_retriever()
        elapsed = time.time() - start
        print(f"[App] Startup complete in {elapsed:.1f}s - {len(retriever.products)} products indexed")
    except Exception as e:
        print(f"[App] WARNING: Startup error: {e}")
        traceback.print_exc()
    yield
    print("[App] Shutting down")


app = FastAPI(
    title="SHL Assessment Recommender",
    description="Conversational agent for recommending SHL Individual Test Solutions",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@app.get("/chat")
async def chat_usage():
    return {
        "message": "Use POST /chat with a JSON body containing messages.",
        "example": {
            "messages": [
                {"role": "user", "content": "Hiring a Java developer with stakeholder skills"}
            ]
        },
        "docs": "/docs",
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        start = time.time()
        
        if not request.messages:
            return ChatResponse(
                reply="Hello! I'm the SHL Assessment Recommender. I can help you find the right assessments for your hiring needs. What role are you looking to hire for?",
                recommendations=[],
                end_of_conversation=False,
            )
    
        response = handle_chat(request.messages)
        
        elapsed = time.time() - start
        print(f"[Chat] Processed in {elapsed:.1f}s | Recs: {len(response.recommendations)} | EOC: {response.end_of_conversation}")
        
        return response
        
    except Exception as e:
        print(f"[Chat] Error: {e}")
        traceback.print_exc()
        
        return ChatResponse(
            reply="I apologize for the technical difficulty. Could you please rephrase your question about SHL assessments?",
            recommendations=[],
            end_of_conversation=False,
        )


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")
