"""Public file serving with a resolved directory boundary."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


def public_file(root: Path, requested: str) -> FileResponse:
    root = root.resolve()
    candidate = (root / requested).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(404, "Not found")
    if requested.split("/", 1)[0] in {"api", "ws"}:
        raise HTTPException(404, "Not found")
    # Only compiled assets and explicitly shipped public files are downloadable.
    if requested and (
        requested.startswith("assets/") or requested in {"favicon.svg", "icons.svg"}
    ):
        if not candidate.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(candidate)
    if any(part.startswith(".") for part in Path(requested).parts):
        raise HTTPException(404, "Not found")
    return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
