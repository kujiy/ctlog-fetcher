import datetime as dt
from datetime import datetime
from typing import List

from fastapi import Depends, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import JST
from src.manager_api.base_models import UploadCertItem, UploadResponse
from src.manager_api.db import get_async_session
from src.manager_api.routers.worker_upload2 import upload_certificates2

router = APIRouter()

@router.post("/api/worker/upload")
async def upload_certificates(
    items: List[UploadCertItem],
    db: AsyncSession = Depends(get_async_session)
) -> UploadResponse:
    return await upload_certificates2(items, db)
