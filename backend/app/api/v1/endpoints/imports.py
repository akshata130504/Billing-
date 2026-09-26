"""CSV import API (contract section 10, Data import). Mounted at /imports."""
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.core.exceptions import ValidationAppError
from backend.app.models import ImportEntity
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.schemas.imports import ImportResult
from backend.app.services import import_service as svc
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()

_READ_CHUNK_BYTES = 64 * 1024


@router.get("", response_model=PaginatedResponse[ImportResult], summary="Import history")
def list_imports(
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_imports(db, ctx, params)
    return page.to_response(svc.serialize_job)


@router.get(
    "/templates/{entity}",
    response_class=Response,
    summary="Download the CSV template for an entity",
    responses={200: {"content": {"text/csv": {}}}},
)
def import_template(entity: ImportEntity, ctx: CurrentContext = Depends(require_viewer)):
    return Response(
        content=svc.template_csv(entity),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{entity.value}_template.csv"'},
    )


@router.post("/{entity}", response_model=ImportResult, status_code=status.HTTP_200_OK, summary="Import a CSV file")
async def run_import(
    entity: ImportEntity,
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    # Read in bounded chunks: never buffer more than MAX_FILE_BYTES (+1 chunk) of an
    # oversized upload into memory just to reject it afterwards.
    chunks = []
    size = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        size += len(chunk)
        if size > svc.MAX_FILE_BYTES:
            raise ValidationAppError("CSV file is larger than 5 MB.", {"fields": {"file": "too large"}})
        chunks.append(chunk)
    content = b"".join(chunks)
    file_name = file.filename or f"{entity.value}.csv"
    return svc.run_import(db, ctx, entity, file_name, content, dry_run)
