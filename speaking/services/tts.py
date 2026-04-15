from openai import OpenAI
import tempfile

client = OpenAI()


async def text_to_voice(text: str):
    try:
        response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text
        )

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.write(response.content)
        temp_file.close()

        return open(temp_file.name, "rb")

    except Exception as e:
        print("TTS ERROR:", e)
        return None