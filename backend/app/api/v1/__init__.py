from fastapi import APIRouter

from app.api.v1 import areas, auth, health, me, properties, search, stats, tools

router = APIRouter()
router.include_router(health.router)
router.include_router(properties.router)
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(stats.router)
router.include_router(search.router)
router.include_router(tools.router)
router.include_router(areas.router)
