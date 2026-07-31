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
    waiting_antispam_threshold = State()
    waiting_gt_rules_text = State()
    waiting_gt_rules_time = State()
    waiting_gt_autokick_silent = State()
    waiting_gt_minreg = State()


class ProfileStates(StatesGroup):
    waiting_gender = State()
    waiting_city = State()
    waiting_birthday = State()
    waiting_birthday_visibility = State()
    waiting_motto = State()
    waiting_description = State()
    waiting_nickname = State()
    waiting_title = State()
