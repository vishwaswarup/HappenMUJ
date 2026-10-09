from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.core.errors import ErrorResponse
from app.models.common import to_oid
from app.services import files as svc

router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/{file_id}",
    responses={200: {"content": {"image/*": {}}}, 304: {}, 404: {"model": ErrorResponse}},
    summary="Stream a poster from GridFS (immutable, so cached aggressively)",
)
async def get_file(file_id: str, request: Request):
    oid = to_oid(file_id, "file id")
    etag = f'"{oid}"'
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "ETag": etag}
    # A replaced poster gets a new id, so a given id never changes: safe to cache forever.
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    stream = await svc.open_file(oid)

    async def body():
        while chunk := await stream.readchunk():
            yield chunk

    meta = stream.metadata or {}
    return StreamingResponse(
        body(),
        media_type=meta.get("content_type", "application/octet-stream"),
        headers={**headers, "Content-Length": str(stream.length)},
    )
