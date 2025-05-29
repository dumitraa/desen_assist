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
        q = select(EditEvent).order_by(EditEvent.id.desc())
        return [event.model_dump() for event in s.exec(q.limit(limit)).all()]


@app.get("/stats/layers")
def layer_stats(month: str | None = None):
    """Return insert/update/delete totals per layer, optionally filtered by month."""
    start_date_obj: datetime.date | None = None
    next_month_start_date_obj: datetime.date | None = None

    if month:
        try:
            year, m = map(int, month.split("-"))
            current_month_start_date = datetime.date(year, m, 1)
            start_date_obj = current_month_start_date
            # Calculate the first day of the next month
            if m == 12:
                next_month_start_date_obj = datetime.date(year + 1, 1, 1)
            else:
                next_month_start_date_obj = datetime.date(year, m + 1, 1)
        except ValueError:
            print(f"Warning: Invalid month format '{month}' for layer_stats. No month filter applied for layers.")
            # Keep start_date_obj and next_month_start_date_obj as None

    with Session(engine) as s:
        q_base = select(
            LayerStat.layer_name,
            func.sum(LayerStat.adds).label("total_adds"),
            func.sum(LayerStat.updates).label("total_updates"),
            func.sum(LayerStat.deletes).label("total_deletes"),
        )

        if start_date_obj and next_month_start_date_obj:
            q = q_base.where(
                LayerStat.date >= start_date_obj,
                LayerStat.date < next_month_start_date_obj
            ).group_by(LayerStat.layer_name)
        else: # No month filter or invalid month
            q = q_base.group_by(LayerStat.layer_name)

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
    selected_month_start_date: datetime.date
    if month:
        try:
            year, m_val = map(int, month.split("-"))
            selected_month_start_date = datetime.date(year, m_val, 1)
        except ValueError:
            today = datetime.date.today()
            selected_month_start_date = today.replace(day=1)
            print(f"Warning: Invalid month format '{month}'. Defaulting to current month for KM stats: {selected_month_start_date.strftime('%Y-%m')}")
    else:
        today = datetime.date.today()
        selected_month_start_date = today.replace(day=1)
    next_month_first_day_for_layerstat = (
        selected_month_start_date.replace(day=28) + datetime.timedelta(days=4)
    ).replace(day=1)

    # Determine timestamp range for EditEvent query (for active users)
    month_start_datetime = datetime.datetime.combine(selected_month_start_date, datetime.time.min)
    
    # Calculate the first day of the next month for timestamp end range
    if selected_month_start_date.month == 12:
        next_month_first_day_for_timestamp = datetime.datetime(selected_month_start_date.year + 1, 1, 1)
    else:
        next_month_first_day_for_timestamp = datetime.datetime(selected_month_start_date.year, selected_month_start_date.month + 1, 1)
    
    start_timestamp = month_start_datetime.timestamp()
    end_timestamp = next_month_first_day_for_timestamp.timestamp()

    number_of_active_users = 0
    dynamic_target_km = 0.0  # Default to 0.0, will be updated
    progress = None

    with Session(engine) as s:
        # Get number of active users in the selected month
        active_users_query = select(func.count(func.distinct(EditEvent.user))).where(
            EditEvent.ts >= start_timestamp,
            EditEvent.ts < end_timestamp
        )
        count_result = s.scalar(active_users_query)
        if count_result is not None:
            number_of_active_users = count_result

        # Get total KM for TRONSON_JT for the selected month from LayerStat
        km_query = (
            select(LayerStat.date, func.sum(LayerStat.kilometers).label("daily_total_km"))
            .where(
                LayerStat.layer_name == "TRONSON_JT",
                LayerStat.date >= selected_month_start_date,
                LayerStat.date < next_month_first_day_for_layerstat,
            )
            .group_by(LayerStat.date)
            .order_by(LayerStat.date)
        )
        rows = s.exec(km_query).all()

        daily_km_data = {str(r.date): r.daily_total_km for r in rows}
        total_km_for_month = sum(r.daily_total_km for r in rows if r.daily_total_km is not None)

        # Use MONTHLY_TARGET_KM from config as the per-user target
        per_user_monthly_target = MONTHLY_TARGET_KM

        if per_user_monthly_target is not None:
            try:
                per_user_target_float = float(per_user_monthly_target)
                if number_of_active_users > 0:
                    dynamic_target_km = number_of_active_users * per_user_target_float
                else: 
                    dynamic_target_km = 0.0

                if dynamic_target_km != 0.0:
                    progress = total_km_for_month / dynamic_target_km
                elif total_km_for_month == 0.0: 
                    progress = 1.0 
                else: 
                    progress = None 
            except (ValueError, TypeError) as e:
                print(f"Error with MONTHLY_TARGET_KM ('{per_user_monthly_target}'): {e}")
                dynamic_target_km = 0.0 
                progress = None
        else: #
            dynamic_target_km = 0.0
            progress = 1.0 if total_km_for_month == 0.0 else None


        return {
            "month": selected_month_start_date.strftime("%Y-%m"),
            "daily_km": daily_km_data,
            "total_km": total_km_for_month,
            "user_target_km": per_user_monthly_target, # Return the configured target
            "total_target": dynamic_target_km, # Return the dynamically calculated target
            "progress": progress,
            "active_users_for_month": number_of_active_users # Optional: for debugging or future display
        }
# MODIFICATION END

@app.get("/stats/users")
def user_stats(month: str | None = None):
    """Return edit counts, session totals, and total kilometers per user for a given month."""
    
    start_timestamp: float | None = None
    end_timestamp: float | None = None

    if month:
        try:
            year, m = map(int, month.split("-"))
            month_start_date = datetime.date(year, m, 1)
            
            # Calculate the first day of the next month
            if m == 12:
                next_month_start_date = datetime.date(year + 1, 1, 1)
            else:
                next_month_start_date = datetime.date(year, m + 1, 1)
            
            # Convert to datetime objects at midnight for timestamp conversion
            month_start_datetime = datetime.datetime.combine(month_start_date, datetime.time.min)
            next_month_start_datetime = datetime.datetime.combine(next_month_start_date, datetime.time.min)
            
            start_timestamp = month_start_datetime.timestamp()
            end_timestamp = next_month_start_datetime.timestamp()
            
        except ValueError:
            print(f"Warning: Invalid month format '{month}' for user_stats. No month filter applied.")
            # Keep start_timestamp and end_timestamp as None to fetch all data

    with Session(engine) as s:
        # Base queries
        q_edits_base = select(EditEvent.user, EditEvent.action, func.count().label("action_count")) # type: ignore
        q_sessions_base = select(EditEvent.user, func.count().label("session_count")).where(EditEvent.action == "session_start") # type: ignore
        q_km_data_base = select(EditEvent.user, EditEvent.wkt).where(
            EditEvent.layer == "TRONSON_JT",
            EditEvent.wkt.isnot(None),
            EditEvent.wkt != ""
        )

        # Apply month filter if timestamps are available
        if start_timestamp is not None and end_timestamp is not None:
            time_filter = (EditEvent.ts >= start_timestamp, EditEvent.ts < end_timestamp)
            q_edits = q_edits_base.where(*time_filter).group_by(EditEvent.user, EditEvent.action)
            q_sessions = q_sessions_base.where(*time_filter).group_by(EditEvent.user)
            q_km_data = q_km_data_base.where(*time_filter)
        else: # No month filter
            q_edits = q_edits_base.group_by(EditEvent.user, EditEvent.action)
            q_sessions = q_sessions_base.group_by(EditEvent.user)
            q_km_data = q_km_data_base


        edits_data = {}
        for user, action, cnt in s.exec(q_edits):
            user_entry = edits_data.setdefault(user, {
                "adds": 0, "updates": 0, "deletes": 0, "sessions": 0, "total_km": 0.0
            })
            if action == "add":
                user_entry["adds"] += cnt
            elif action == "delete":
                user_entry["deletes"] += cnt
            elif action in ("attr", "geom"):
                user_entry["updates"] += cnt
        
        sessions_results = s.exec(q_sessions).all()
        for user, count in sessions_results:
            user_entry = edits_data.setdefault(user, {
                "adds": 0, "updates": 0, "deletes": 0, "sessions": 0, "total_km": 0.0
            })
            user_entry["sessions"] = count

        km_events = s.exec(q_km_data).all()
        user_km_totals = {}
        for user, wkt_geometry in km_events:
            if wkt_geometry: # Should always be true due to query filter, but good practice
                length = _length_km(wkt_geometry)
                user_km_totals[user] = user_km_totals.get(user, 0.0) + length
        
        for user, data in edits_data.items():
            data["total_km"] = round(user_km_totals.get(user, 0.0), 3)

        return [
            {
                "user": user_key,
                "sessions": data["sessions"],
                "adds": data["adds"],
                "updates": data["updates"],
                "deletes": data["deletes"],
                "total_km": data["total_km"]
            }
            for user_key, data in edits_data.items()
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