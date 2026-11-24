import io
import json
from pathlib import Path
import pandas as pd
from fastapi import HTTPException

ALLOWED = {"csv", "json"}

def inspect_upload(filename: str | None, payload: bytes):
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    if suffix not in ALLOWED:
        raise HTTPException(415, "Upload a CSV or JSON file.")
    if not payload:
        raise HTTPException(400, "The uploaded file is empty.")
    try:
        text = payload.decode("utf-8-sig")
        first = text.lstrip()[:1]
        if first in {"{", "["}:
            try:
                json.loads(text)
                if suffix != "json":
                    raise HTTPException(400, "The file contents do not match the .csv extension.")
            except json.JSONDecodeError:
                if suffix == "json":
                    raise
        if suffix == "csv":
            frame = pd.read_csv(io.BytesIO(payload), encoding="utf-8-sig")
        else:
            raw = json.loads(text)
            if isinstance(raw, dict):
                raw = raw.get("data") if isinstance(raw.get("data"), list) else [raw]
            if not isinstance(raw, list) or any(not isinstance(row, dict) for row in raw):
                raise ValueError("JSON must contain an object or a list of objects.")
            frame = pd.DataFrame(raw)
        if frame.empty and len(frame.columns) == 0:
            raise ValueError("No tabular columns were found.")
        return suffix, frame
    except (UnicodeDecodeError, json.JSONDecodeError, pd.errors.ParserError, ValueError) as exc:
        raise HTTPException(400, "The file contents are not valid tabular CSV or JSON.") from exc

def column_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series): return "boolean"
    if pd.api.types.is_integer_dtype(series): return "integer"
    if pd.api.types.is_numeric_dtype(series): return "number"
    if pd.api.types.is_datetime64_any_dtype(series): return "datetime"
    return "string"

def read_preview(path: Path, fmt: str, limit: int):
    try:
        if not path.is_file():
            raise FileNotFoundError(path.name)
        if fmt == "csv":
            frame = pd.read_csv(path, nrows=limit)
            return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = raw.get("data", [raw]) if isinstance(raw, dict) and isinstance(raw.get("data"), list) else raw
        if isinstance(rows, dict): rows = [rows]
        return rows[:limit]
    except Exception as exc:
        raise HTTPException(404, "Dataset content is unavailable.") from exc
