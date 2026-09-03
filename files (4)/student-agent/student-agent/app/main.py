from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import agent, students, whatsapp

# Creates tables if they don't exist. Fine for the prototype/MVP; once you have
# real data, switch to Alembic migrations (see architecture doc Section 20)
# instead of relying on create_all.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Student Intelligence System — Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your actual web frontend origin before going live
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router)
app.include_router(students.router)
app.include_router(whatsapp.router)

# Serves the simple web chat page at /app/index.html
app.mount("/app", StaticFiles(directory="web", html=True), name="web")


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs", "web_chat": "/app/index.html"}
