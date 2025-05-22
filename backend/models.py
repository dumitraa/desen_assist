from sqlmodel import SQLModel, Field
from typing import Optional
import datetime

class EditEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: float
    action: str = Field(default="")
    layer: Optional[str] = None
    fid: Optional[int] = None
    field: Optional[str] = None
    value: Optional[str] = None
    wkt:  Optional[str] = None
    user: str = Field(default="unknown")
    extra: Optional[str] = None

    def dict(self, **kw):
        d = super().dict(**kw)
        # human date for dashboard
        d["time"] = datetime.datetime.fromtimestamp(self.ts).isoformat()
        return d

class LayerStat(SQLModel, table=True):
    """Aggregated daily statistics for each layer."""

    id: Optional[int] = Field(default=None, primary_key=True)
    date: datetime.date
    layer_name: str
    adds: int = 0
    updates: int = 0
    deletes: int = 0
    kilometers: float = 0.0

    def dict(self, **kw):
        d = super().dict(**kw)
        d["date"] = self.date.isoformat()
        return d