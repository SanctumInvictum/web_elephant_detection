from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import shutil
from uuid import uuid4

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


@router.post("/")
async def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix
    filename = f"{uuid4()}{ext}"
    file_path = UPLOAD_DIR / filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return JSONResponse({
        "filename": filename,
        "url": f"/static/uploads/{filename}"
    })


@router.get("/preview/{filename}")
async def preview_file(filename: str):
    file_path = UPLOAD_DIR / filename
    return FileResponse(file_path)

