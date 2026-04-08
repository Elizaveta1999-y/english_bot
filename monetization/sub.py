import datetime
from config import TRIAL_DAYS

users = {}

def init_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "start": datetime.datetime.now(),
            "sub": False
        }

def has_access(user_id):
    u = users[user_id]
    days = (datetime.datetime.now() - u["start"]).days
    return u["sub"] or days < TRIAL_DAYS