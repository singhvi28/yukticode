import contextlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router, mq
from .auth import router as auth_router
from .admin import router as admin_router

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await mq.connect()
    yield
    # Shutdown
    await mq.close()

app = FastAPI(lifespan=lifespan)

# Allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],  # * added for ease in dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(admin_router)

