from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pathlib import Path
import shutil
import uuid
from datetime import datetime
import json
from ultralytics import YOLO
import os
import subprocess

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "app" / "static" / "uploads"
PROCESSED_DIR = BASE_DIR / "app" / "static" / "processed"
HISTORY_FILE = BASE_DIR / "app" / "data" / "history.json"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = BASE_DIR / "models" / "elephant_model.pt"
model = YOLO(MODEL_PATH)
model.fuse()


@router.post("/")
async def process_file(request: Request):
    try:
        data = await request.json()
        filename = data.get("filename")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not filename:
        raise HTTPException(status_code=422, detail="Missing 'filename' in request")

    input_path = UPLOAD_DIR / filename

    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Input file not found")

    # Обработка через YOLO с явным указанием пути
    runs_dir = BASE_DIR / "runs" / "detect"
    results = model(
        input_path,
        save=True,
        project=str(runs_dir),
        name="predict",
        exist_ok=True
    )

    detection_data = []
    for result in results:
        for box in result.boxes:
            detection_data.append({
                "class_id": int(box.cls),
                "confidence": float(box.conf),
                "bbox": box.xywhn.tolist()[0]  # Нормализованные координаты
            })

    # Явное сохранение результатов
    for r in results:
        r.save()

    # Поиск последней папки
    latest_folder = max(
        (d for d in runs_dir.glob("predict*") if d.is_dir()),
        key=os.path.getmtime,
        default=None
    )

    if not latest_folder:
        raise RuntimeError("No output folder created by YOLO")

    # Рекурсивный поиск файлов результатов
    output_files = list(latest_folder.rglob("*.*"))
    output_files = [f for f in output_files if f.suffix.lower() in ('.mp4', '.jpg', '.png', '.avi')]

    if not output_files:
        raise RuntimeError(f"No result files found in {latest_folder}")

    # Копирование первого найденного файла
    output_file = output_files[0]
    new_name = f"{uuid.uuid4()}{output_file.suffix}"
    processed_path = PROCESSED_DIR / new_name
    shutil.copy(output_file, processed_path)

    if output_file.suffix.lower() == '.avi':
        mp4_path = processed_path.with_suffix('.mp4')
        subprocess.run([
            'ffmpeg', '-i', str(processed_path),
            '-c:v', 'libx264', '-preset', 'fast',
            '-crf', '23', '-c:a', 'aac', '-b:a', '128k',
            str(mp4_path)
        ], check=True)
        processed_path.unlink()  # Удаляем оригинальный AVI
        new_name = mp4_path.name  # Обновляем имя файла для ответа

    # Запись в историю
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "input_file": filename,
        "output_file": new_name,
        "processing_time": results[0].speed.get("inference", 0) if results else 0,
        "detections": {
            "total_elephants": len(detection_data),
            "average_confidence": round(
                (sum(d['confidence'] for d in detection_data) / len(detection_data))
                if detection_data else 0,
                4
            ),
            "detections_list": detection_data
        }
    }

    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []

        history.append(record)

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    except Exception as e:
        print("Failed to update history:", e)

    return JSONResponse({"processed_file": new_name})


