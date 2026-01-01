import asyncio
import base64
from dataclasses import asdict, dataclass
import os
import re
import sys
from typing import Any, Literal

import aiohttp
import discord
from dotenv import load_dotenv

SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"}
]

@dataclass
class Part:
    text: str

@dataclass
class Content:
    parts: list[Part]
    role: Literal["user", "model"]

@dataclass
class Contents:
    contents: list[Content]
    safety_settings: list[dict[str, Any]]
    generationConfig: dict[str, Any]

load_dotenv()

MAX_HISTORY_SIZE = 10

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


DEFAULT_MODEL = "gemma-3-27b-it"
GEMINI_MODEL = "gemini-2.5-flash-lite"
DEFAULT_PROMPT = "short to medium sized answer"
MAX_OUTPUT_TOKEN = 2048


class MyClient(discord.Client):
    api_key = os.environ["GEMINI_API_KEY"]
    model = DEFAULT_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    default_status = "Genshin Impact"

    prompt: str = DEFAULT_PROMPT
    history = Contents(
        contents=[], 
        safety_settings=SAFETY_SETTINGS,  
        generationConfig={"max_output_tokens": MAX_OUTPUT_TOKEN}
    )

    lock = asyncio.Lock()

    async def set_status(self, text: str):
        await self.change_presence(
            status=discord.Status.online, activity=discord.Game(text)
        )

    def reset_history(self):
        self.history.contents = []

    def trim_chat(self):
        self.history.contents = self.history.contents[-MAX_HISTORY_SIZE:]

    async def send_post_request(self, payload, url_override: str | None = None) -> str:
        # print(payload)
        # print("")

        if url_override:
            url = url_override
        else:
            url = self.url


        async with aiohttp.ClientSession() as session:
            response = await session.post(url, headers=self.headers, json=payload)
            data = await response.json()
            # print("")
            # print(data)
            # print("")

        try:
            response_text: str = data["candidates"][0]["content"]["parts"][0]["text"]
        except:
            self.history.contents.pop()
            raise Exception(data)

        self.add_to_history(response_text, "model")

        if "gemini" in url:
            return f"Gemini: {response_text}"
        return response_text

    def add_to_history(self, message: str, role: Literal["user", "model"]):
        self.history.contents.append(Content(
            role=role,
            parts=[Part(text=message)]
            )
        )

    async def send_text_message(self, message: str):
        self.add_to_history(message, "user")

        print("Sending text message...")
        await self.set_status("Processing text...")
        return await self.send_post_request(asdict(self.history))

    async def send_picture_video(self, message: str, image: bytes, mime: str):
        self.add_to_history(message, "user")

        base64_str = base64.b64encode(image).decode("utf-8")

        payload = {
            "contents": {
                "role": "user",
                "parts": [
                    {"text": message},
                    {"inlineData": {
                        "data": base64_str, "mimeType": mime }
                    }
                ]
            },
            "safety_settings": SAFETY_SETTINGS,
            "generationConfig": {"max_output_tokens": MAX_OUTPUT_TOKEN}
        }

        if mime in VIDEO_MIMES:
            print("Sending video...")
            await self.set_status("Processing video...")
            temp_url = self.url.replace(self.model, GEMINI_MODEL)
            return await self.send_post_request(payload, temp_url)

        print("Sending picture...")
        await self.set_status("Processing picture...")
        return await self.send_post_request(payload)

    async def send_youtube_link(self, message: str, link: str):
        self.add_to_history(message, "user")

        payload = {
            "contents": {
                "parts":[
                    {"text": message},
                    {"file_data": {
                        "file_uri": link }
                    }
                ]
            },
            "safety_settings": SAFETY_SETTINGS,
            "generationConfig": {"max_output_tokens": MAX_OUTPUT_TOKEN}
        }

        temp_url = self.url.replace(self.model, GEMINI_MODEL)
        print("Sending youtube link...")
        await self.set_status("Processing youtube link...")
        return await self.send_post_request(payload, temp_url)

    async def on_ready(self):
        print(f"Logged on as {self.user}!")
        await self.set_status(self.default_status)

    async def on_message(self, message):
        async with self.lock:
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
                    if len(self.history.contents) == 0:
                        await message.reply("No message history", mention_author=True)
                        return

                    response = ""
                    for msg in self.history.contents:
                        text = msg.parts[0].text[:64].replace("\n", " ") # type: ignore
                        if len(text) >= 64:
                            text += "..."
                        response += f"{msg.role}: {text}\n\n"

                    await message.reply(response, mention_author=True)
                    return

                if user_message in ("!new", "!neu", "!reset"):
                    print("Reseting history...")
                    self.prompt = DEFAULT_PROMPT
                    self.reset_history()
                    await message.reply("Cleared conversation!", mention_author=True)
                    return

                if user_message.startswith("!status"):
                    self.default_status = user_message.removeprefix("!status").strip()
                    print(f"Changing status to '{self.default_status}'")
                    await self.set_status(self.default_status)
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
                    if len(self.history.contents) == 0:
                        await message.reply(
                            "There are no messages to delete",
                            mention_author=True,
                        )
                    elif len(self.history.contents) <= 2:
                        self.reset_history()
                        await message.reply(
                            "Deleted the last 2 messages! No more messages left.",
                            mention_author=True,
                        )
                    else:
                        self.history.contents = self.history.contents[:-2]
                        last_message = (
                            self.history.contents[-1]
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

                await message.channel.typing()

                # add prompt after message
                user_message = f"{user_message} [{self.prompt}]"

                if len(message.attachments) > 0:
                    mime = message.attachments[0].content_type

                    if mime == "video/quicktime":
                        mime = "video/mov"

                    if mime in IMAGE_MIMES or mime in VIDEO_MIMES:  # if picture or video
                        # download attachment
                        async with aiohttp.ClientSession() as session:
                            async with session.get(message.attachments[0].url) as resp:
                                image_bytes = await resp.read()
                        response = await self.send_picture_video(user_message, image_bytes, mime)

                    else:
                        raise ValueError(f"Unsupported attachment type {mime}")
                # elif user_message.startswith(("https://www.youtube.com/", "https://youtu.be")):
                #     link, text = user_message.split(" ", 1)
                #     response = await self.send_youtube_link(text, link)
                else:
                    response = await self.send_text_message(user_message)

                # delete older messages
                self.trim_chat()

                response = str(response)  # pyright: ignore[reportPossiblyUnboundVariable]


                # don't quote discord ID
                response_text = re.sub(r'`(<@[0-9]+>)`', r'\1', response)
                # forward response to discord
                CHUNK_SIZE = 2000
                for i in range(0, len(response_text), CHUNK_SIZE):
                    chunk = response_text[i : i + CHUNK_SIZE]
                    await message.reply(chunk, mention_author=True)


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
            finally:
                try:
                    await self.set_status(self.default_status)
                except Exception as e:
                    print(e)


intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(os.environ["DISCORD_TOKEN"])
