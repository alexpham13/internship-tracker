from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import Base, database_path, get_session, make_engine
from .models import Application, ImportedApplication
from .schemas import (
    ApplicationFields,
    ApplicationImport,
    ApplicationRecord,
    ApplicationStatus,
    Health,
    ImportResult,
    Statistics,
)

DatabaseSession = Annotated[Session, Depends(get_session)]


def create_app(path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(path if path is not None else database_path())
        try:
            Base.metadata.create_all(engine)
            app.state.engine = engine
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="InternTrack AI API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://{host}:{port}"
            for host in ("localhost", "127.0.0.1")
            for port in (5173, 5174)
        ],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health(db: DatabaseSession) -> Health:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise HTTPException(503, "Database unavailable.") from error
        return Health(status="ok")

    @app.get("/applications", response_model=list[ApplicationRecord])
    def list_applications(db: DatabaseSession):
        return db.scalars(
            select(Application).order_by(Application.date_applied.desc(), Application.id)
        ).all()

    @app.post("/applications", status_code=201, response_model=ApplicationRecord)
    def create_application(fields: ApplicationFields, db: DatabaseSession):
        application = Application(id=str(uuid4()), **fields.model_dump())
        db.add(application)
        db.commit()
        return application

    @app.post("/applications/import")
    def import_applications(batch: ApplicationImport, db: DatabaseSession) -> ImportResult:
        imported = 0
        for record in batch.applications:
            claimed_id = db.scalar(
                insert(ImportedApplication).values(id=record.id)
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(ImportedApplication.id)
            )
            if claimed_id is None:
                continue
            inserted_id = db.scalar(
                insert(Application).values(**record.model_dump())
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(Application.id)
            )
            imported += inserted_id is not None
        db.commit()
        return ImportResult(imported=imported, skipped=len(batch.applications) - imported)

    @app.put("/applications/{id}", response_model=ApplicationRecord)
    def update_application(id: str, fields: ApplicationFields, db: DatabaseSession):
        application = find_application(db, id)
        for field, value in fields.model_dump().items():
            setattr(application, field, value)
        db.commit()
        return application

    @app.delete("/applications/{id}", status_code=204)
    def delete_application(id: str, db: DatabaseSession) -> Response:
        db.delete(find_application(db, id))
        db.commit()
        return Response(status_code=204)

    @app.get("/statistics")
    def statistics(db: DatabaseSession) -> Statistics:
        total, responses, interviews, offers = db.execute(
            select(
                func.count(Application.id),
                func.count(case((Application.status != ApplicationStatus.APPLIED, 1))),
                func.count(case((Application.status == ApplicationStatus.INTERVIEW, 1))),
                func.count(case((Application.status == ApplicationStatus.OFFER, 1))),
            )
        ).one()
        return Statistics(total=total, responses=responses, interviews=interviews, offers=offers)

    return app


def find_application(db: Session, id: str) -> Application:
    application = db.get(Application, id)
    if application is None:
        raise HTTPException(404, "Application not found.")
    return application


app = create_app()
