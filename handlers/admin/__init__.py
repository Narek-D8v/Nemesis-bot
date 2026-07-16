from aiogram import Router
from . import ranks, warns, punish, misc
from .common import is_mod_cmd, CMD_PATTERNS, RANK_NAMES, get_reason, check_rank, get_min_rank, parse_cmd_rank

router = Router()

router.include_router(ranks.router)
router.include_router(warns.router)
router.include_router(punish.router)
router.include_router(misc.router)
