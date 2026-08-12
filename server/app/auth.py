from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from . import store
from .database import get_session
from .db_models import ParticipantRow
from .security import decode_admin_token

_bearer = HTTPBearer(auto_error=False)


async def get_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少管理员凭据")
    username = decode_admin_token(credentials.credentials)
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员凭据无效")
    if await store.admin_by_username(session, username) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员凭据无效")
    return username


async def get_participant(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> ParticipantRow:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少参与者凭据")
    participant = await store.participant_by_token(session, credentials.credentials)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="参与者凭据无效")
    return participant
