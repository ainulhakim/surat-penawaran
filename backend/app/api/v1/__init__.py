from fastapi import APIRouter

from app.api.v1 import auth, clients, dashboard, execution, master, penawaran, users, wilayah

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(wilayah.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(master.router)
api_router.include_router(penawaran.router)
api_router.include_router(execution.router)
api_router.include_router(dashboard.router)
