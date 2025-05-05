from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import FileResponse
from pathlib import Path
import json
import pandas as pd

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE_DIR / "history.json"


class HistoryEntry(BaseModel):
    filename: str
    processed: bool
    timestamp: str


@router.post("/save")
def save_history(entry: HistoryEntry):
    history = []
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r") as f:
            history = json.load(f)
    history.append(entry.dict())
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)
    return {"status": "saved"}


@router.get("/export/excel")
def export_excel():
    if not HISTORY_PATH.exists():
        return {"error": "No history found"}
    df = pd.read_json(HISTORY_PATH)
    export_path = BASE_DIR / "report.xlsx"
    df.to_excel(export_path, index=False)
    return FileResponse(export_path)

