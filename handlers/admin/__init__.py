from aiogram import Router
from . import ranks, warns, punish, misc

router = Router()

router.include_router(ranks.router)
router.include_router(warns.router)
router.include_router(punish.router)
router.include_router(misc.router)
