"""JobHunt API and static host.

Routes are grouped by concern and all of them except /api/auth/* require a
signed session cookie. The frontend is plain static files served from web/.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import (Cookie, Depends, FastAPI, File, HTTPException, Response,
                     UploadFile, status)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import WEB_DIR, settings
from .cvgen import CvDocument, CvRequest, rerender
from .cvmine import MAX_FILES, mine
from .docx import build_docx, filename_for
from .cvgen import build as build_cv
from .importer import ImportError_, to_applications
from .models import (
    Application,
    ApplicationList,
    Credentials,
    ImportRequest,
    Profile,
    PromptRequest,
    PublicUser,
    now_iso,
)
from .prompts import build as build_prompt
from .security import hash_password, make_session, read_session, verify_password
from .storage import StorageError, get_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("jobhunt")

app = FastAPI(title=settings.app_name, docs_url="/api/docs", openapi_url="/api/openapi.json")


# --------------------------------------------------------------------------
# dependencies
# --------------------------------------------------------------------------
def current_user_id(jobhunt_session: Optional[str] = Cookie(default=None)) -> str:
    user_id = read_session(jobhunt_session)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return user_id


def load_profile(user_id: str) -> Profile:
    raw = get_store().get_profile(user_id)
    return Profile(**raw) if raw else Profile()


def load_applications(user_id: str) -> list[dict[str, Any]]:
    return get_store().list_applications(user_id) or []


@app.exception_handler(StorageError)
async def _storage_error(_request, exc: StorageError):
    log.error("storage: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.middleware("http")
async def no_store(request, call_next):
    """Never let the browser cache anything this app serves.

    The frontend is read straight off disk and edited live, and API responses
    are per-user state. A cached asset means you are running yesterday's code;
    a cached error response means the app keeps reporting a failure that was
    fixed several restarts ago. Both have happened.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
def _set_session(response: Response, user_id: str) -> None:
    response.set_cookie(
        settings.session_cookie,
        make_session(user_id),
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@app.post("/api/auth/register", response_model=PublicUser)
def register(credentials: Credentials, response: Response) -> PublicUser:
    store = get_store()
    if store.get_user_by_email(credentials.email):
        raise HTTPException(409, "An account already exists for that email address.")
    user = store.create_user(credentials.email, hash_password(credentials.password))
    store.save_profile(user["id"], Profile(identity={"email": user["email"]}).model_dump())
    _set_session(response, user["id"])
    log.info("registered %s", user["email"])
    return PublicUser(id=user["id"], email=user["email"], created_at=user["created_at"])


@app.post("/api/auth/login", response_model=PublicUser)
def login(credentials: Credentials, response: Response) -> PublicUser:
    user = get_store().get_user_by_email(credentials.email)
    # Same message either way - which of the two was wrong is not the
    # caller's business.
    if not user or not verify_password(credentials.password, user.get("password_hash", "")):
        raise HTTPException(401, "Email or password is incorrect.")
    _set_session(response, user["id"])
    return PublicUser(id=user["id"], email=user["email"], created_at=user["created_at"])


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(settings.session_cookie, path="/")
    return {"ok": True}


@app.get("/api/auth/me", response_model=PublicUser)
def me(user_id: str = Depends(current_user_id)) -> PublicUser:
    user = get_store().get_user(user_id)
    if not user:
        raise HTTPException(401, "Session no longer valid.")
    return PublicUser(id=user["id"], email=user["email"], created_at=user["created_at"])


# --------------------------------------------------------------------------
# profile
# --------------------------------------------------------------------------
@app.get("/api/profile")
def get_profile(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    profile = load_profile(user_id)
    return {"profile": profile.model_dump(), "completeness": profile.completeness()}


@app.put("/api/profile")
def put_profile(profile: Profile, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    saved = get_store().save_profile(user_id, profile.model_dump())
    return {"profile": saved, "completeness": Profile(**saved).completeness()}


# --------------------------------------------------------------------------
# applications
# --------------------------------------------------------------------------
@app.get("/api/applications")
def get_applications(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    return {"applications": load_applications(user_id)}


@app.put("/api/applications")
def put_applications(
    payload: ApplicationList, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    # The client sends the whole list, so only bump updated_at on rows that
    # actually differ. Stamping every row would make "nothing has moved in 30
    # days" impossible to detect.
    stored = {a.get("id"): a for a in load_applications(user_id) if a.get("id")}

    rows = []
    for application in payload.applications:
        if not application.id:
            application.id = str(uuid.uuid4())
        incoming = application.model_dump()
        previous = stored.get(application.id)
        if previous is None or _differs(previous, incoming):
            incoming["updated_at"] = now_iso()
        else:
            incoming["updated_at"] = previous.get("updated_at", incoming["updated_at"])
        rows.append(incoming)

    get_store().save_applications(user_id, rows)
    return {"applications": rows}


def _differs(previous: dict[str, Any], incoming: dict[str, Any]) -> bool:
    """Compare two applications ignoring the timestamp we are deciding about."""
    skip = {"updated_at"}
    keys = (set(previous) | set(incoming)) - skip
    return any(previous.get(k) != incoming.get(k) for k in keys)


# --------------------------------------------------------------------------
# prompts - the Hunt button
# --------------------------------------------------------------------------
@app.post("/api/prompt")
def make_prompt(request: PromptRequest, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    profile = load_profile(user_id)

    application: Application | None = None
    if request.application_id:
        match = next(
            (a for a in load_applications(user_id) if a.get("id") == request.application_id),
            None,
        )
        if match is None:
            raise HTTPException(404, "That application is not in your tracker.")
        application = Application(**match)

    try:
        return build_prompt(profile, request, application)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# --------------------------------------------------------------------------
# import an assistant's reply
# --------------------------------------------------------------------------
@app.post("/api/import")
def import_reply(payload: ImportRequest, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    existing = load_applications(user_id)
    try:
        result = to_applications(payload.text, existing)
    except ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc

    batch = now_iso()
    for application in result["applications"]:
        application.id = str(uuid.uuid4())
        application.import_batch = batch
        existing.append(application.model_dump())

    if result["applications"]:
        get_store().save_applications(user_id, existing)

    return {
        "batch": batch if result["applications"] else "",
        "found": result["found"],
        "imported": result["imported"],
        "duplicates": result["duplicates"],
        "skipped": result["skipped"],
        "applications": existing,
    }


# --------------------------------------------------------------------------
# CV generation - no AI call, pure selection and ordering
# --------------------------------------------------------------------------
@app.post("/api/cv")
def make_cv(request: CvRequest, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    profile = load_profile(user_id)

    application: Application | None = None
    if request.application_id:
        match = next(
            (a for a in load_applications(user_id) if a.get("id") == request.application_id),
            None,
        )
        if match is None:
            raise HTTPException(404, "That application is not in your tracker.")
        application = Application(**match)

    if not profile.evidence or not any(i for g in profile.evidence for i in g.items if i.strip()):
        raise HTTPException(
            400, "Your evidence bank is empty, so there is nothing to build a CV from."
        )

    return build_cv(profile, request, application).model_dump()


@app.post("/api/cv/docx")
def cv_as_docx(document: CvDocument, user_id: str = Depends(current_user_id)) -> Response:
    """The CV as an editable Word document, in the profile's house style."""
    profile = load_profile(user_id)
    data = build_docx(
        document,
        font=profile.doc_prefs.font or "Calibri",
        accent=profile.doc_prefs.accent or "#1F3864",
    )
    name = filename_for(document)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.post("/api/cv/render")
def render_cv(document: CvDocument, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Re-render a CV the user has edited in the browser."""
    profile = load_profile(user_id)
    return rerender(document, profile.doc_prefs.max_pages).model_dump()


# --------------------------------------------------------------------------
# mining an existing CV - the alternative to a blank questionnaire
# --------------------------------------------------------------------------
@app.post("/api/mine")
async def mine_cvs(
    files: list[UploadFile] = File(...),
    user_id: str = Depends(current_user_id),
) -> dict[str, Any]:
    """Read candidates out of uploaded CVs. Writes nothing to the profile."""
    if not files:
        raise HTTPException(400, "No files were uploaded.")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload at most {MAX_FILES} CVs at a time.")

    payload: list[tuple[str, bytes]] = []
    for upload in files:
        name = (upload.filename or "cv.docx").rsplit("/", 1)[-1]
        if not name.lower().endswith(".docx"):
            raise HTTPException(
                400, f"{name} is not a .docx. Word documents only for now - "
                     "a PDF has no reliable structure to read."
            )
        payload.append((name, await upload.read()))

    # Anything already recorded is not offered again as a suggestion.
    profile = load_profile(user_id)
    known: list[str] = list(profile.boundaries)
    for group in profile.evidence:
        known.extend(group.items)
    for job in profile.employment:
        known.extend(job.bullets)
        known.append(job.note)
    for item in profile.independent:
        known.extend(item.bullets)
        known.append(item.description)

    result = mine(payload, known=known)
    if not result["files_read"]:
        raise HTTPException(422, "None of those files could be read as Word documents.")
    log.info("mined %s file(s) for %s: %s candidates",
             result["files_read"], user_id, len(result["candidates"]))
    return result


# --------------------------------------------------------------------------
# meta
# --------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "storage": get_store().describe(),
        "backend": settings.storage_backend,
    }


# --------------------------------------------------------------------------
# static frontend - mounted last so it never shadows /api
# --------------------------------------------------------------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    # index.html carries an inline SVG icon; browsers still ask for this and
    # the 404s were the only noise in the log.
    return Response(status_code=204)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
