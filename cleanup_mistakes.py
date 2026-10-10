import asyncio
from dotenv import load_dotenv

load_dotenv()

from handlers.tutor import _clean_mistake
from utils.db import tutor_get_memory, tutor_update_memory


USER_ID = 6115540828


async def cleanup():
    m = await tutor_get_memory(USER_ID)
    raw = m.get("active_mistakes") or []

    clean = []
    for x in raw:
        c = _clean_mistake(x)
        if c and c not in clean:
            clean.append(c)

    cur = _clean_mistake(m.get("current_mistake"))

    print("БЫЛО  active :", raw)
    print("СТАЛО active :", clean)
    print("БЫЛО  current:", m.get("current_mistake"))
    print("СТАЛО current:", cur)

    await tutor_update_memory(
        USER_ID,
        active_mistakes=clean,
        current_mistake=cur,
    )
    print("Готово.")


asyncio.run(cleanup())