from openai import OpenAI
import tempfile

client = OpenAI()


async def voice_to_text(file_bytes: bytes) -> str:
    try:
        # сохраняем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # отправляем в OpenAI
        with open(tmp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file
            )

        return transcript.text

    except Exception as e:
        print("STT ERROR:", e)
        return ""