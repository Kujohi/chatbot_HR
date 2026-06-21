from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.services.auth_service import (
    build_login_redirect,
    complete_login,
    get_current_user,
    logout_response,
)

router = APIRouter(prefix="/auth")


@router.get("/login")
async def login(request: Request, return_to: str | None = None):
    return build_login_redirect(request, return_to=return_to)


@router.get("/callback")
async def callback(request: Request, code: str, state: str):
    return complete_login(request, code=code, state=state)


@router.get("/me")
async def me(request: Request):
    user = get_current_user(request)
    return {"status": "success", "data": user}


@router.post("/logout")
async def logout():
    return logout_response()

