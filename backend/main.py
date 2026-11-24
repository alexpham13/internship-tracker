import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import pymupdf
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import URL, case, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import (
    CSRF_HEADER, CurrentUser, DatabaseSession, configure_auth, current_user, login, register,
    router as auth_router,
)
from .cover_letter import generate_cover_letter, router as cover_letter_router
from .database import conflict_insert, make_engine
from .migrations import initialize_schema
from .models import Application, ImportedApplication
from .resume_analysis import analyze_resume, router as resume_analysis_router
from .schemas import (
    ApplicationFields,
    ApplicationImport,
    ApplicationRecord,
    ApplicationStatus,
    Health,
    ImportResult,
    Statistics,
)

MAX_RESUME_SIZE = 5 * 1024 * 1024


def create_app(path: Path | str | URL | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(path)
        try:
            initialize_schema(engine)
            app.state.engine = engine
            # Keep PyMuPDF calls on one thread without blocking the event loop.
            with ThreadPoolExecutor(max_workers=1) as pdf_executor:
                app.state.pdf_executor = pdf_executor
                yield
        finally:
            engine.dispose()

    app = FastAPI(title="InternTrack AI API", lifespan=lifespan)
    configure_auth(app)
    app.include_router(auth_router)
    app.include_router(resume_analysis_router, dependencies=[Depends(current_user)])
    app.include_router(cover_letter_router, dependencies=[Depends(current_user)])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app.state.auth_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER],
    )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, error: RequestValidationError):
        endpoint = request.scope.get("endpoint")
        if endpoint in (login, register):
            detail = "Enter a valid email address and password."
            if endpoint is register:
                detail = "Enter a name (up to 100 characters), a valid email address, and a password of 15–128 characters."
            return JSONResponse(status_code=422, content={"detail": detail}, headers={"Cache-Control": "no-store"})
        if endpoint in (analyze_resume, generate_cover_letter):
            detail = "Provide resume text and a job description, each up to 30,000 characters."
            if endpoint is generate_cover_letter:
                detail += " Select a professional, enthusiastic, or concise tone."
            return JSONResponse(
                status_code=422,
                content={"detail": detail},
                headers={"Cache-Control": "no-store"},
            )
        return await request_validation_exception_handler(request, error)

    @app.get("/health")
    def health(db: DatabaseSession) -> Health:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise HTTPException(503, "Database unavailable.") from error
        return Health(status="ok")

    @app.post("/resume/extract", dependencies=[Depends(current_user)])
    async def extract_resume(
        file: Annotated[UploadFile, File()], request: Request, response: Response
    ) -> dict[str, str]:
        if file.size is not None and file.size > MAX_RESUME_SIZE:
            raise HTTPException(413, "The resume must be 5 MB or smaller.")
        if not (file.filename or "").lower().endswith(".pdf") or file.content_type not in (
            None, "", "application/pdf", "application/octet-stream",
        ):
            raise HTTPException(415, "Choose a PDF resume.")

        content = await file.read(MAX_RESUME_SIZE + 1)
        if len(content) > MAX_RESUME_SIZE:
            raise HTTPException(413, "The resume must be 5 MB or smaller.")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(415, "This file is not a valid PDF.")

        resume_text = await asyncio.get_running_loop().run_in_executor(
            request.app.state.pdf_executor, extract_pdf_text, content
        )
        response.headers["Cache-Control"] = "no-store"
        return {"text": resume_text}

    @app.get("/applications", response_model=list[ApplicationRecord])
    def list_applications(db: DatabaseSession, user: CurrentUser):
        return db.scalars(
            select(Application).where(Application.user_id == user.id).order_by(Application.date_applied.desc(), Application.id)
        ).all()

    @app.post("/applications", status_code=201, response_model=ApplicationRecord)
    def create_application(fields: ApplicationFields, db: DatabaseSession, user: CurrentUser):
        application = Application(id=str(uuid4()), user_id=user.id, **fields.model_dump())
        db.add(application)
        db.commit()
        return application

    @app.post("/applications/import")
    def import_applications(batch: ApplicationImport, db: DatabaseSession, user: CurrentUser) -> ImportResult:
        imported = 0
        # Consistent lock order prevents overlapping PostgreSQL imports from deadlocking.
        for record in sorted(batch.applications, key=lambda item: item.id):
            claimed_id = db.scalar(
                conflict_insert(db, ImportedApplication).values(id=record.id, user_id=user.id)
                .on_conflict_do_nothing(index_elements=["user_id", "id"])
                .returning(ImportedApplication.id)
            )
            if claimed_id is None:
                continue
            inserted_id = db.scalar(
                conflict_insert(db, Application).values(user_id=user.id, **record.model_dump())
                .on_conflict_do_nothing(index_elements=["user_id", "id"])
                .returning(Application.id)
            )
            imported += inserted_id is not None
        db.commit()
        return ImportResult(imported=imported, skipped=len(batch.applications) - imported)

    @app.put("/applications/{id}", response_model=ApplicationRecord)
    def update_application(id: str, fields: ApplicationFields, db: DatabaseSession, user: CurrentUser):
        application = find_application(db, user.id, id)
        for field, value in fields.model_dump().items():
            setattr(application, field, value)
        db.commit()
        return application

    @app.delete("/applications/{id}", status_code=204)
    def delete_application(id: str, db: DatabaseSession, user: CurrentUser) -> Response:
        db.delete(find_application(db, user.id, id))
        db.commit()
        return Response(status_code=204)

    @app.get("/statistics")
    def statistics(db: DatabaseSession, user: CurrentUser) -> Statistics:
        total, responses, interviews, offers = db.execute(
            select(
                func.count(Application.id),
                func.count(case((Application.status != ApplicationStatus.APPLIED, 1))),
                func.count(case((Application.status == ApplicationStatus.INTERVIEW, 1))),
                func.count(case((Application.status == ApplicationStatus.OFFER, 1))),
            ).where(Application.user_id == user.id)
        ).one()
        return Statistics(total=total, responses=responses, interviews=interviews, offers=offers)

    return app


def extract_pdf_text(content: bytes) -> str:
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise HTTPException(422, "Remove the PDF password and upload it again.")
            pages = [page.get_text(sort=True).strip() for page in document]
    except (RuntimeError, ValueError) as error:
        raise HTTPException(422, "Could not read this PDF. Export it again and retry.") from error

    resume_text = "\n\n".join(filter(None, pages))
    if not resume_text:
        raise HTTPException(
            422, "This PDF has no extractable text. Upload a PDF with selectable text or paste your resume below."
        )
    return resume_text


def find_application(db: Session, user_id: str, id: str) -> Application:
    application = db.scalar(select(Application).where(Application.user_id == user_id, Application.id == id))
    if application is None:
        raise HTTPException(404, "Application not found.")
    return application


app = create_app()
