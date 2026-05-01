from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import engine, Base
import app.models  # registers all models with Base before create_all
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
