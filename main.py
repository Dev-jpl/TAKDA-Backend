from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routers import knowledge, spaces

load_dotenv()

app = FastAPI(title="TAKDA API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge.router)
app.include_router(spaces.router)

@app.get("/")
def root():
    return {"status": "TAKDA backend running"}

@app.get("/health")
def health():
    return {"status": "ok"}