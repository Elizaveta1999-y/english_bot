# check.py
try:
    from data.lesson_data import LESSON_CONTENT
    print("SUCCESS:", list(LESSON_CONTENT.keys()))
except Exception as e:
    print("ERROR:", e)
    import traceback
    traceback.print_exc()