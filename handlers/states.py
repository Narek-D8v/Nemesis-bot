from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    waiting_greeting = State()
    waiting_farewell = State()
    waiting_blacklist_word = State()
    waiting_blacklist_word_remove = State()
    waiting_whitelist_user_add = State()
    waiting_whitelist_user_remove = State()
    waiting_daily_rules_text = State()
    waiting_daily_rules_time = State()
    waiting_night_start = State()
    waiting_night_end = State()
    waiting_night_action = State()
