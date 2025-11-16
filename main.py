import os
import sys
from dotenv import load_dotenv
import discord
from google import genai
from google.genai import types
import requests
# from threading import Timer

load_dotenv()

MODEL_NAME = "gemini-2.5-flash-lite"
MAX_HISTORY_SIZE = 20
SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
]

VIDEO_MIMES = (
    "video/mp4",
    "video/mpeg",
    "video/mov",
    "video/avi",
    "video/x-flv",
    "video/mpg",
    "video/webm",
    "video/wmv",
    "video/3gpp",
)

IMAGE_MIMES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
)

DEFUALT_CONFIG = types.GenerateContentConfig(
    safety_settings=SAFETY_SETTINGS,
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    maxOutputTokens=2048,
)


DEFAULT_PROMPT = "short to medium sized answer"


def new_api_key(current_api_key, api_keys):
    index = api_keys.index(current_api_key)
    next_index = (index + 1) % len(api_keys)
    print(f"Gemini api key index was set to {next_index}")
    return api_keys[next_index]


def new_client(new_api_key):
    return genai.Client(api_key=new_api_key)


def new_chat(client):
    return client.chats.create(
        model=MODEL_NAME,
        config=DEFUALT_CONFIG,
    )


def trim_chat(client, chat):
    return client.chats.create(
        model=MODEL_NAME,
        config=DEFUALT_CONFIG,
        history=chat.get_history()[-MAX_HISTORY_SIZE:],
    )


def undo_message(client, chat):
    return client.chats.create(
        model=MODEL_NAME,
        config=DEFUALT_CONFIG,
        history=chat.get_history()[:-2],
    )


class MyClient(discord.Client):
    api_keys = []

    for i in range(32):
        env_api_key = os.getenv(f"GEMINI_API_KEY{i}")
        if env_api_key:
            api_keys.append(env_api_key)

    print(f"Found {len(api_keys)} gemini api keys!")

    prompt: str = DEFAULT_PROMPT

    current_api_key = api_keys[0]
    client = new_client(current_api_key)
    chat = new_chat(client)

    # reset_timer = None

    async def on_ready(self):
        print(f"Logged on as {self.user}!")
        await self.change_presence(
            status=discord.Status.online, activity=discord.Game("Genshin Impact")
        )

    async def on_message(self, message):
        try:
            if message.author.id == self.user.id:
                return

            user_message: str = message.content

            if user_message == "":
                return

            if user_message == "!restart":
                print("Exiting...")
                sys.exit(0)

            if user_message == "!history":
                print("Getting history...")
                if len(self.chat.get_history()) == 0:
                    await message.reply("No message history", mention_author=True)
                    return

                response = ""
                for msg in self.chat.get_history():
                    text = msg.parts[0].text[:64].replace("\n", " ")
                    if len(text) >= 64:
                        text += "..."
                    response += f"{msg.role}: {text}\n\n"

                await message.reply(response, mention_author=True)
                return

            if user_message == "!new" or user_message == "!resetgemini":
                print("Reseting history...")
                self.prompt = DEFAULT_PROMPT
                self.chat = new_chat(self.client)
                await message.reply("Cleared gemini conversation!", mention_author=True)
                return

            if user_message.startswith("!prompt"):
                new_prompt = user_message.removeprefix("!prompt").strip()
                if new_prompt:
                    self.prompt = f"{new_prompt}, {DEFAULT_PROMPT}"
                else:
                    self.prompt = DEFAULT_PROMPT

                print(f"Prompt was set to {self.prompt}")
                return

            if user_message == "!undo" or user_message == "!revert":
                print("Deleting last 2 messages...")
                if len(self.chat.get_history()) == 0:
                    await message.reply(
                        "There are no messages to delete",
                        mention_author=True,
                    )
                elif len(self.chat.get_history()) <= 2:
                    self.chat = new_chat(self.client)
                    await message.reply(
                        "Deleted the last 2 messages! No more messages left.",
                        mention_author=True,
                    )
                else:
                    self.chat = undo_message(self.client, self.chat)
                    last_message = (
                        self.chat.get_history()[-1]
                        .parts[0]
                        .text[:128]
                        .replace("\n", " ")
                    )
                    if len(last_message) >= 128:
                        last_message += "..."
                    await message.reply(
                        f"Deleted last 2 messages! Current last message begins with:\n\n{last_message}",
                        mention_author=True,
                    )
                return

            mentioned: bool = user_message.startswith(f"<@{self.user.id}>")
            if mentioned:
                user_message = user_message.replace(f"<@{self.user.id}>", "", 1).strip()

            question_mark: bool = user_message.startswith("?")
            if question_mark:
                user_message = user_message.replace("?", "", 1).strip()

            reply: bool = False
            if message.reference:
                replied_message = await message.channel.fetch_message(
                    message.reference.message_id
                )
                if replied_message.author.id == self.user.id:
                    reply = True

            if not mentioned and not question_mark and not reply:
                return

            # def reset():
            #     print("Reset timer finished, clearing history...")
            #     self.prompt = DEFAULT_PROMPT
            #     self.chat = new_chat(self.client)

            # if self.reset_timer:
            #     self.reset_timer.cancel()
            #     self.reset_timer = None

            # self.reset_timer = Timer(7200, reset)
            # self.reset_timer.start()

            await message.channel.typing()

            # add prompt after message
            user_message = f"{user_message} [{self.prompt}]"

            if len(message.attachments) > 0:
                mime = message.attachments[0].content_type

                if mime == "video/quicktime":
                    mime = "video/mov"

                if mime in IMAGE_MIMES:  # if picture
                    # download attachment
                    image_bytes = requests.get(message.attachments[0].url).content

                    # send in isolated conversation since can't send image in multi turn conversation
                    response = self.client.models.generate_content(
                        model=MODEL_NAME,
                        contents=[
                            user_message,
                            types.Part.from_bytes(data=image_bytes, mime_type=mime),
                        ],
                        config=DEFUALT_CONFIG,
                    )

                elif mime in VIDEO_MIMES:  # if video
                    # download attachment
                    video_bytes = requests.get(message.attachments[0].url).content

                    response = self.client.models.generate_content(
                        model=MODEL_NAME,
                        contents=types.Content(
                            parts=[
                                types.Part(
                                    inline_data=types.Blob(
                                        data=video_bytes, mime_type=mime
                                    )
                                ),
                                types.Part(text=user_message),
                            ]
                        ),
                        config=DEFUALT_CONFIG,
                    )

                else:
                    raise ValueError(f"Unsupported attachment type {mime}")

                # add this response to the multi turn chat history manually
                self.chat.get_history().append(
                    types.UserContent(parts=[types.Part(user_message)])
                )
                self.chat.get_history().append(
                    types.Content(role="model", parts=[types.Part(response.text)])
                )
            elif user_message.startswith(
                ("https://www.youtube.com/", "https://youtu.be")
            ):
                link, text = user_message.split(" ", 1)

                response = self.client.models.generate_content(
                    model=MODEL_NAME,
                    contents=types.Content(
                        parts=[
                            types.Part(file_data=types.FileData(file_uri=link)),
                            types.Part(text=text),
                        ]
                    ),
                    config=DEFUALT_CONFIG,
                )

                # add this response to the multi turn chat history manually
                self.chat.get_history().append(
                    types.UserContent(parts=[types.Part(user_message)])
                )
                self.chat.get_history().append(
                    types.Content(role="model", parts=[types.Part(response.text)])
                )
            else:
                response = self.chat.send_message(user_message)

            # delete older messages
            self.chat = trim_chat(self.client, self.chat)

            # forward gemini's response to discord
            CHUNK_SIZE = 2000
            for i in range(0, len(response.text), CHUNK_SIZE):
                chunk = response.text[i : i + CHUNK_SIZE]
                await message.reply(chunk, mention_author=True)

        except Exception as e:
            try:
                error_text = str(e)
                error_text = error_text.replace(
                    self.current_api_key, "GEMINI_TOKEN_HERE"
                )
                error_text = error_text.replace(
                    os.getenv("DISCORD_TOKEN"), "DISCORD_TOKEN_HERE"
                )
                print(error_text)

                if "429 RESOURCE_EXHAUSTED" in error_text:
                    # change api key
                    self.current_api_key = new_api_key(
                        self.current_api_key, self.api_keys
                    )

                    # set new api key to client
                    self.client = new_client(self.current_api_key)

                    # workaround as new client requires new chat
                    self.chat = trim_chat(self.client, self.chat)

                    await message.reply(
                        "Api key limit reached, changed to new, continue spamming",
                        mention_author=True,
                    )
                else:
                    await message.reply(error_text, mention_author=True)
            except Exception as discord_error:
                print(discord_error)


intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(os.getenv("DISCORD_TOKEN"))
