import secrets
from typing import Annotated

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBasicCredentials, HTTPBasic
from starlette import status

from src.config import config

security = HTTPBasic()


def basic_auth(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> HTTPBasicCredentials:
    current_username_bytes = credentials.username.encode("utf8")
    current_password_bytes = credentials.password.encode("utf8")

    correct_username = config.auth_user.encode()
    correct_password = config.auth_pass.encode()
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username
    )
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password
    )

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect auth creds",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials
