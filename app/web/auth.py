from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import token_matches
from app.templates import templates

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(request: Request, token: str = Form(...)):
    if not token_matches(token):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid token"}, status_code=401
        )
    request.session["token"] = token
    return RedirectResponse(url="/dashboard/invoices", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
