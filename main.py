from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routers import knowledge, spaces, track, hubs, annotate, deliver, automate, coordinator, events

load_dotenv()

app = FastAPI(title="TAKDA API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(spaces.router)
app.include_router(hubs.router)
app.include_router(knowledge.router)
app.include_router(track.router)
app.include_router(annotate.router)
app.include_router(deliver.router)
app.include_router(events.router)
app.include_router(coordinator.router, prefix="/coordinator")

@app.get("/")
def root():
    return {"status": "TAKDA backend running"}

@app.get("/health")
def health():
    return {"status": "ok"}