from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlmodel import Session, select
from .database import engine, init_db
from .models import EditEvent

app = FastAPI(title="Digitizer Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",   # VS-Code Live-Server
        "http://localhost:3000", 
        "file://",                
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

@app.post("/events")
def add_event(ev: EditEvent):
    with Session(engine) as s:
        s.add(ev)
        s.commit()
    return {"ok": True}

@app.get("/events")
def list_events(limit: int = 100):
    with Session(engine) as s:
        q = select(EditEvent).order_by(EditEvent.id.desc()).limit(limit)
        return [row.dict() for row in s.exec(q)]
