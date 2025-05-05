from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from typing import List, Dict
from pathlib import Path
import json
import pandas as pd
from reportlab.pdfgen import canvas
from io import BytesIO
import openpyxl
import xlsxwriter

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Поднимаемся на уровень выше
HISTORY_PATH = BASE_DIR / "app" / "data" / "history.json"  # Полный корректный путь


class DetectionInfo(BaseModel):
    class_id: int
    confidence: float
    bbox: List[float]

class HistoryEntry(BaseModel):
    input_file: str
    output_file: str
    timestamp: str
    processing_time: float  # ms
    detections: Dict[str, object]


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
    try:
        if not HISTORY_PATH.exists():
            return {"error": "No history found"}

        with open(HISTORY_PATH, "r") as f:
            history = json.load(f)

        # Создаем DataFrame с защитой от отсутствующих полей
        rows = []
        for entry in history:
            row = {
                "Timestamp": entry.get("timestamp", ""),
                "Input File": entry.get("input_file", ""),
                "Output File": entry.get("output_file", ""),
                "Processing Time (ms)": entry.get("processing_time", 0),
                "Total Elephants": entry.get("detections", {}).get("total_elephants", 0),
                "Avg Confidence": round(entry.get("detections", {}).get("average_confidence", 0), 3)
            }
            rows.append(row)

        df = pd.DataFrame(rows)

        # Добавляем вычисляемые поля
        if not df.empty:
            df["Detection Rate"] = df["Total Elephants"] / df.groupby("Input File")["Input File"].transform("count")
        else:
            df["Detection Rate"] = 0

        export_path = BASE_DIR / "report.xlsx"

        # Сохраняем с явным указанием движка
        with pd.ExcelWriter(export_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Summary', index=False)

            # Детализированные данные
            details = []
            for entry in history:
                for det in entry.get("detections", {}).get("detections_list", []):
                    details.append({
                        "Input File": entry.get("input_file", ""),
                        "Timestamp": entry.get("timestamp", ""),
                        "Class ID": det.get("class_id", -1),
                        "Confidence": det.get("confidence", 0),
                        "BBox Center X": det.get("bbox", [0, 0, 0, 0])[0],
                        "BBox Center Y": det.get("bbox", [0, 0, 0, 0])[1],
                        "BBox Width": det.get("bbox", [0, 0, 0, 0])[2],
                        "BBox Height": det.get("bbox", [0, 0, 0, 0])[3]
                    })

            pd.DataFrame(details).to_excel(writer, sheet_name='Detections', index=False)

        return FileResponse(export_path)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Excel generation failed: {str(e)}"}
        )


@router.get("/export/pdf")
def export_pdf():
    if not HISTORY_PATH.exists():
        return {"error": "No history found"}

    with open(HISTORY_PATH, "r") as f:
        history = json.load(f)

    buffer = BytesIO()
    p = canvas.Canvas(buffer)

    # Заголовок
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "Detection Statistics Report")

    # Основная статистика
    p.setFont("Helvetica", 12)
    y = 750
    total_detections = sum(entry["detections"]["total_elephants"] for entry in history)
    avg_confidence = sum(entry["detections"]["average_confidence"] for entry in history) / len(
        history) if history else 0

    p.drawString(100, y, f"Total files processed: {len(history)}")
    p.drawString(100, y - 30, f"Total elephants detected: {total_detections}")
    p.drawString(100, y - 60, f"Average confidence: {avg_confidence:.2f}")


    p.showPage()
    p.save()

    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition": "attachment;filename=report.pdf"})


@router.get("/summary")
def get_summary():
    print("Checking history at:", HISTORY_PATH)  # Отладочная информация
    if not HISTORY_PATH.exists():
        print("History file not found!")  # Логирование ошибки
        return {"error": "No history found"}

    with open(HISTORY_PATH, "r") as f:
        history = json.load(f)

    total_files = len(history)
    total_elephants = sum(entry["detections"]["total_elephants"] for entry in history)
    avg_processing_time = sum(entry["processing_time"] for entry in history) / total_files if total_files > 0 else 0

    return {
        "total_files_processed": total_files,
        "total_elephants_detected": total_elephants,
        "average_processing_time_ms": avg_processing_time,
        "detection_per_file": [{
            "file": entry["input_file"],
            "detections": entry["detections"]["total_elephants"]
        } for entry in history]
    }