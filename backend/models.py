from sqlmodel import SQLModel, Field
from typing import Optional
import datetime, json

class EditEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: float                      
    layer: str
    fid: int
    field: Optional[int] = None
    value: Optional[str] = None
    wkt:  Optional[str] = None
    user: str = Field(default="unknown")

    def dict(self, **kw):
        d = super().dict(**kw)
        # human date for dashboard
        d["time"] = datetime.datetime.fromtimestamp(self.ts).isoformat()
        return d
