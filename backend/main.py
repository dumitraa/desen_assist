from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # Import this
from fastapi.responses import HTMLResponse  # Import this
from pathlib import Path # Import this

from sqlmodel import Session, select
from sqlalchemy import func, desc
from database import engine, init_db
from models import EditEvent, LayerStat

from math import hypot

import datetime

from config import MONTHLY_TARGET_KM

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


def _length_km(wkt: str) -> float:
    """Very small WKT parser for LINESTRING/MULTILINESTRING lengths."""
    if not wkt:
        return 0.0
    wkt = wkt.strip()
    if wkt.upper().startswith("MULTILINESTRING"):
        inner = wkt[wkt.find("((") + 2 : wkt.rfind("))")]
        parts = inner.split("),(")
        return sum(_length_km(f"LINESTRING({p})") for p in parts)
    if not wkt.upper().startswith("LINESTRING"):
        return 0.0
    coords_text = wkt[wkt.find("(") + 1 : wkt.rfind(")")]
    pts = [tuple(map(float, p.split())) for p in coords_text.split(",")]
    length = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        length += hypot(x2 - x1, y2 - y1)
    return length / 1000.0


app = FastAPI(title="Digitizer Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000", 
        "http://localhost:3000",
        "file://",
        "http://localhost:8000", 
                                 # makes requests to itself (the API on the same origin)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# API Endpoints
@app.post("/events")
def add_event(ev: EditEvent):
    with Session(engine) as s:
        s.add(ev)
        # update stats -------------------------------------------------
        if ev.layer:
            day = datetime.date.fromtimestamp(ev.ts)
            st = s.exec(
                select(LayerStat).where(
                    LayerStat.date == day, LayerStat.layer_name == ev.layer
                )
            ).first()
            if not st:
                st = LayerStat(date=day, layer_name=ev.layer)
            if ev.action == "add":
                st.adds += 1
            elif ev.action == "delete":
                st.deletes += 1
            elif ev.action in ("attr", "geom"):
                st.updates += 1
            if ev.layer == "TRONSON_JT" and ev.wkt:
                st.kilometers += _length_km(ev.wkt)
            s.add(st)
        s.commit()
    return {"ok": True}

@app.get("/events")
def list_events(limit: int = 100):
    with Session(engine) as s:
        q = select(EditEvent).order_by(EditEvent.id.desc()) # type: ignore[attr-defined]
        return [row.model_dump() for row in s.exec(q)]


@app.get("/stats/layers")
def layer_stats():
    """Return insert/update/delete totals per layer."""
    with Session(engine) as s:
        q = (
            select(
                LayerStat.layer_name,
                func.sum(LayerStat.adds),
                func.sum(LayerStat.updates),
                func.sum(LayerStat.deletes),
            )
            .group_by(LayerStat.layer_name)
        )
        rows = s.exec(q).all()
        return [
            {
                "layer_name": r[0],
                "adds": r[1] or 0,
                "updates": r[2] or 0,
                "deletes": r[3] or 0,
            }
            for r in rows
        ]


@app.get("/stats/kilometers")
def kilometers_stats(month: str | None = None):
    """Return daily kilometers and progress for TRONSON_JT."""
    if month:
        year, m = map(int, month.split("-"))
        start = datetime.date(year, m, 1)
    else:
        today = datetime.date.today()
        start = today.replace(day=1)
    next_month = (
        start.replace(day=28) + datetime.timedelta(days=4)
    ).replace(day=1)
    with Session(engine) as s:
        q = (
            select(LayerStat.date, func.sum(LayerStat.kilometers)) # type: ignore[call-arg]
            .where(
                LayerStat.layer_name == "TRONSON_JT",
                LayerStat.date >= start,
                LayerStat.date < next_month,
            )
            .group_by(LayerStat.date)
            .order_by(LayerStat.date)
        )
        rows = s.exec(q).all()
        daily = {str(r[0]): r[1] for r in rows}
        total = sum(daily.values())
        progress = (
            total / MONTHLY_TARGET_KM if MONTHLY_TARGET_KM else None
        )
        return {
            "month": start.strftime("%Y-%m"),
            "daily_km": daily,
            "total_km": total,
            "target_km": MONTHLY_TARGET_KM,
            "progress": progress,
        }


@app.get("/stats/users")
def user_stats():
    """Return edit counts per user and session totals."""
    with Session(engine) as s:
        q_edits = (
            select(EditEvent.user, EditEvent.action, func.count())
            .group_by(EditEvent.user, EditEvent.action)
        )
        q_sessions = (
            select(EditEvent.user, func.count())
            .where(EditEvent.action == "session_start")
            .group_by(EditEvent.user)
        )
        edits = {}
        for user, action, cnt in s.exec(q_edits):
            e = edits.setdefault(user, {"adds": 0, "updates": 0, "deletes": 0})
            if action == "add":
                e["adds"] += cnt
            elif action == "delete":
                e["deletes"] += cnt
            elif action in ("attr", "geom"):
                e["updates"] += cnt
        sessions = {u: c for u, c in s.exec(q_sessions)}
        return [
            {
                "user": user,
                "sessions": sessions.get(user, 0),
                "adds": data["adds"],
                "updates": data["updates"],
                "deletes": data["deletes"],
            }
            for user, data in edits.items()
        ]


# 1. Create a route for the root path "/" to serve index.html
@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    index_path = DASHBOARD_DIR / "index.html"
    if index_path.is_file():
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>index.html not found</h1>", status_code=404)

app.mount("/dashboard_assets", StaticFiles(directory=DASHBOARD_DIR), name="dashboard_assets")