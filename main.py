import os
import re
import sys

import discord
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

# from threading import Timer

load_dotenv()

MODEL_NAME = "gemma-3-27b-it"
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
    # thinking_config=types.ThinkingConfig(thinking_budget=0),
    max_output_tokens=2048,
    # tools=[types.Tool(google_search=types.GoogleSearch())]
)


DEFAULT_PROMPT = "short to medium sized answer"



def new_client():
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


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
    prompt: str = DEFAULT_PROMPT

    client = new_client()
    chat = new_chat(client)

    # reset_timer = None

    async def on_ready(self):
        print(f"Logged on as {self.user}!")
        await self.change_presence(
            status=discord.Status.online, activity=discord.Game("Genshin Impact")
        )

    async def on_message(self, message):
        try:
            if not self.user: # to stop pylance from crying
                return
            
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
                    text = msg.parts[0].text[:64].replace("\n", " ") # type: ignore
                    if len(text) >= 64:
                        text += "..."
                    response += f"{msg.role}: {text}\n\n"

                await message.reply(response, mention_author=True)
                return

            if user_message in ("!new", "!neu", "!resetgemini"):
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

            if user_message in ("!undo", "!revert"):
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
                        .parts[0] # type: ignore
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

            if response.text:
                # don't quote discord ID
                response_text =  re.sub(r'`(<@[0-9]+>)`', r'\1', response.text)
                # forward gemini's response to discord
                CHUNK_SIZE = 2000
                for i in range(0, len(response_text), CHUNK_SIZE):
                    chunk = response_text[i : i + CHUNK_SIZE]
                    await message.reply(chunk, mention_author=True)
            else:
                print(response)
                await message.reply("Gemini didn't respond", mention_author=True)

        except Exception as e:
            try:
                error_text = str(e)
                error_text = error_text.replace(
                    os.environ["GEMINI_API_KEY"], "GEMINI_TOKEN_HERE"
                )
                error_text = error_text.replace(
                    os.environ["DISCORD_TOKEN"], "DISCORD_TOKEN_HERE"
                )
                print(error_text)

                await message.reply(error_text, mention_author=True)
            except Exception as discord_error:
                print(discord_error)


intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(os.environ["DISCORD_TOKEN"])
