"""Database construction is explicit so tests never share a production file."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    options = {"connect_args": {"check_same_thread": False}}
    if url == "sqlite://":
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def make_sessions(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
