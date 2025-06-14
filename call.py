import asyncio
import os
from datetime import datetime, timedelta
from typing import Union

from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup
from pytgcalls import PyTgCalls, StreamType
from pytgcalls.exceptions import (
    AlreadyJoinedError,
    NoActiveGroupCall,
    TelegramServerError,
    GroupCallNotFound,
)
from pytgcalls.types import Update
from pytgcalls.types.input_stream import AudioPiped, AudioVideoPiped
from pytgcalls.types.input_stream.quality import HighQualityAudio, MediumQualityVideo
from pytgcalls.types.messages import StreamAudioEnded

import config
from AnonXMusic import LOGGER, YouTube, app
from AnonXMusic.misc import db
from AnonXMusic.utils.database import (
    add_active_chat,
    add_active_video_chat,
    get_loop,
    group_assistant,
    is_autoend,
    music_on,
    remove_active_chat,
    remove_active_video_chat,
    set_loop,
)
from AnonXMusic.utils.exceptions import AssistantErr
from AnonXMusic.utils.formatters import check_duration, seconds_to_min
from AnonXMusic.utils.inline.play import stream_markup
from AnonXMusic.utils.stream.autoclear import auto_clean
from AnonXMusic.utils.thumbnails import get_thumb

autoend = {}
counter = {}

async def clear(chat_id):
    db[chat_id] = []
    await remove_active_video_chat(chat_id)
    await remove_active_chat(chat_id)

class Call(PyTgCalls):
    def __init__(self):
        self.userbot1 = Client(
            name="AnonXAss1",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING1),
        )
        self.one = PyTgCalls(self.userbot1)

        self.userbot2 = Client(
            name="AnonXAss2",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING2),
        )
        self.two = PyTgCalls(self.userbot2)

        self.userbot3 = Client(
            name="AnonXAss3",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING3),
        )
        self.three = PyTgCalls(self.userbot3)

        self.userbot4 = Client(
            name="AnonXAss4",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING4),
        )
        self.four = PyTgCalls(self.userbot4)

        self.userbot5 = Client(
            name="AnonXAss5",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING5),
        )
        self.five = PyTgCalls(self.userbot5)

    async def pause_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await assistant.pause_stream(chat_id)

    async def resume_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await assistant.resume_stream(chat_id)

    async def stop_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        try:
            await clear(chat_id)
            await assistant.leave_group_call(chat_id)
        except GroupCallNotFound:
            pass
        except Exception as e:
            LOGGER(__name__).error(f"Error stopping stream in chat {chat_id}: {e}")
            pass

    async def stop_stream_force(self, chat_id: int):
        assistants = [self.one, self.two, self.three, self.four, self.five]
        for idx, assistant in enumerate(assistants):
            if getattr(config, f"STRING{idx+1}"):
                try:
                    await assistant.leave_group_call(chat_id)
                except GroupCallNotFound:
                    pass
                except Exception as e:
                    LOGGER(__name__).error(f"Error force stopping stream with assistant {idx+1} in chat {chat_id}: {e}")
                    pass
        try:
            await clear(chat_id)
        except Exception as e:
            LOGGER(__name__).error(f"Error clearing chat data for {chat_id}: {e}")
            pass

    async def force_stop_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        try:
            check = db.get(chat_id)
            if check:
                check.pop(0)
        except IndexError:
            pass
        except Exception as e:
            LOGGER(__name__).error(f"Error popping from db for chat {chat_id}: {e}")
            pass

        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        try:
            await assistant.leave_group_call(chat_id)
        except GroupCallNotFound:
            pass
        except Exception as e:
            LOGGER(__name__).error(f"Error leaving group call in force stop for chat {chat_id}: {e}")
            pass

    async def skip_stream(
        self,
        chat_id: int,
        link: str,
        video: Union[bool, str] = None,
        image: Union[bool, str] = None,
    ):
        assistant = await group_assistant(self, chat_id)
        if video:
            stream = AudioVideoPiped(
                link,
                audio_parameters=HighQualityAudio(),
                video_parameters=MediumQualityVideo(),
            )
        else:
            stream = AudioPiped(link, audio_parameters=HighQualityAudio())
        
        await assistant.change_stream(
            chat_id,
            stream,
        )

    async def seek_stream(self, chat_id, file_path, to_seek, duration, mode):
        assistant = await group_assistant(self, chat_id)
        stream = (
            AudioVideoPiped(
                file_path,
                audio_parameters=HighQualityAudio(),
                video_parameters=MediumQualityVideo(),
                additional_ffmpeg_parameters=f"-ss {to_seek}"
            )
            if mode == "video"
            else AudioPiped(
                file_path,
                audio_parameters=HighQualityAudio(),
                additional_ffmpeg_parameters=f"-ss {to_seek}"
            )
        )
        await assistant.change_stream(chat_id, stream)

    async def stream_call(self, link):
        assistant = await group_assistant(self, config.LOGGER_ID)
        try:
            await assistant.join_group_call(
                config.LOGGER_ID,
                AudioVideoPiped(link),
            )
            await asyncio.sleep(0.2)
            await assistant.leave_group_call(config.LOGGER_ID)
        except Exception as e:
            LOGGER(__name__).error(f"Error in stream_call for {link}: {e}")
            raise

    async def join_call(
        self,
        chat_id: int,
        original_chat_id: int,
        link,
        video: Union[bool, str] = None,
        image: Union[bool, str] = None,
    ):
        assistant = await group_assistant(self, chat_id)
        if video:
            stream = AudioVideoPiped(
                link,
                audio_parameters=HighQualityAudio(),
                video_parameters=MediumQualityVideo(),
            )
        else:
            stream = AudioPiped(link, audio_parameters=HighQualityAudio())
        
        try:
            await assistant.join_group_call(
                chat_id,
                stream,
            )
        except NoActiveGroupCall:
            raise AssistantErr("📹 No active video chat found.\nPlease start a video chat in your group or channel and try again.")
        except AlreadyJoinedError:
            raise AssistantErr("⚠️ Assistant is already in a video chat.\n\nIf it's not, please use /reboot and try playing again.")
        except TelegramServerError:
            raise AssistantErr("⚠️ Telegram seems to be facing some internal issues.\n\nPlease try again shortly or restart the video chat in your group.")
        except Exception as e:
            LOGGER(__name__).error(f"Error joining call in chat {chat_id}: {e}")
            raise AssistantErr(f"An unexpected error occurred while joining the call: {e}")

        await add_active_chat(chat_id)
        await music_on(chat_id)
        if video:
            await add_active_video_chat(chat_id)
        if await is_autoend():
            counter[chat_id] = {}
            users = len(await assistant.get_participants(chat_id))
            if users == 1:
                autoend[chat_id] = datetime.now() + timedelta(minutes=1)

    async def change_stream(self, client, chat_id):
        check = db.get(chat_id)
        popped = None
        loop = await get_loop(chat_id)
        try:
            if loop == 0:
                if check: 
                    popped = check.pop(0)
                else:
                    LOGGER(__name__).warning(f"No tracks in queue for chat {chat_id}. Clearing and leaving call.")
                    await clear(chat_id)
                    return await client.leave_group_call(chat_id)
            else:
                loop = loop - 1
            await set_loop(chat_id, loop)
            if popped:
                await auto_clean(popped)
            if not check:
                await clear(chat_id)
                return await client.leave_group_call(chat_id)
        except IndexError:
            LOGGER(__name__).warning(f"Queue is empty for chat {chat_id}. Clearing and leaving call.")
            await clear(chat_id)
            return await client.leave_group_call(chat_id)
        except Exception as e:
            LOGGER(__name__).error(f"Error in change_stream queue handling for chat {chat_id}: {e}")
            try:
                await clear(chat_id)
                return await client.leave_group_call(chat_id)
            except Exception as inner_e:
                LOGGER(__name__).error(f"Error during fallback leave_group_call for chat {chat_id}: {inner_e}")
                return
        else:
            queued = check[0]["file"]
            title = (check[0]["title"]).title()
            user = check[0]["by"]
            original_chat_id = check[0]["chat_id"]
            streamtype = check[0]["streamtype"]
            videoid = check[0]["vidid"]
            db[chat_id][0]["played"] = 0
            exis = (check[0]).get("old_dur")
            if exis:
                db[chat_id][0]["dur"] = exis
                db[chat_id][0]["seconds"] = check[0]["old_second"]
                db[chat_id][0]["speed_path"] = None
                db[chat_id][0]["speed"] = 1.0
            video = True if str(streamtype) == "video" else False
            
            if "live_" in queued:
                n, link = await YouTube.video(videoid, True)
                if n == 0:
                    return await app.send_message(
                        original_chat_id,
                        text="Failed to switch stream, please use /skip to change the track again.",
                    )
                if video:
                    stream = AudioVideoPiped(
                        link,
                        audio_parameters=HighQualityAudio(),
                        video_parameters=MediumQualityVideo(),
                    )
                else:
                    stream = AudioPiped(
                        link,
                        audio_parameters=HighQualityAudio(),
                    )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception as e:
                    LOGGER(__name__).error(f"Error changing live stream for chat {chat_id}: {e}")
                    return await app.send_message(
                        original_chat_id,
                        text="Failed to switch stream, please use /skip to change the track again.",
                    )
                img = await get_thumb(videoid)
                button = stream_markup(chat_id)
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=f"<b>✨ Started Streaming</b>\n\n<b>🎧 Track :</b> {title[:27]}\n<b>⏱️ Duration :</b> {check[0]['dur']} minutes\n<b>🥀 Requested by :</b> {user}",
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"
            elif "vid_" in queued:
                mystic = await app.send_message(original_chat_id, "Downloading next track from queue. Please hold on...")
                try:
                    file_path, direct = await YouTube.download(
                        videoid,
                        mystic,
                        videoid=True,
                        video=True if str(streamtype) == "video" else False,
                    )
                except Exception as e:
                    LOGGER(__name__).error(f"Error downloading video for chat {chat_id}: {e}")
                    return await mystic.edit_text(
                        "Failed to switch stream, please use /skip to change the track again.", disable_web_page_preview=True
                    )
                if video:
                    stream = AudioVideoPiped(
                        file_path,
                        audio_parameters=HighQualityAudio(),
                        video_parameters=MediumQualityVideo(),
                    )
                else:
                    stream = AudioPiped(
                        file_path,
                        audio_parameters=HighQualityAudio(),
                    )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception as e:
                    LOGGER(__name__).error(f"Error changing video stream for chat {chat_id}: {e}")
                    return await app.send_message(
                        original_chat_id,
                        text="Failed to switch stream, please use /skip to change the track again.",
                    )
                img = await get_thumb(videoid)
                button = stream_markup(chat_id)
                await mystic.delete()
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=f"<b>✨ Started Streaming</b>\n\n<b>🎧 Track :</b>  {title[:27]}\n<b>⏱️ Duration :</b> {check[0]['dur']} minutes\n<b>🥀 Requested by :</b> {user}",
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
            elif "index_" in queued:
                stream = (
                    AudioVideoPiped(
                        videoid,
                        audio_parameters=HighQualityAudio(),
                        video_parameters=MediumQualityVideo(),
                    )
                    if str(streamtype) == "video"
                    else AudioPiped(videoid, audio_parameters=HighQualityAudio())
                )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception as e:
                    LOGGER(__name__).error(f"Error changing index stream for chat {chat_id}: {e}")
                    return await app.send_message(
                        original_chat_id,
                        text="Failed to switch stream, please use /skip to change the track again.",
                    )
                button = stream_markup(chat_id)
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=config.STREAM_IMG_URL,
                    caption=f"<b>✨ Started Streaming</b>\n\n<b>🎬 Stream type :</b> Live stream\n<b>🥀 Requested by :</b> {user}",
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"
            else:
                if video:
                    stream = AudioVideoPiped(
                        queued,
                        audio_parameters=HighQualityAudio(),
                        video_parameters=MediumQualityVideo(),
                    )
                else:
                    stream = AudioPiped(
                        queued,
                        audio_parameters=HighQualityAudio(),
                    )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception as e:
                    LOGGER(__name__).error(f"Error changing local/direct stream for chat {chat_id}: {e}")
                    return await app.send_message(
                        original_chat_id,
                        text="Failed to switch stream, please use /skip to change the track again.",
                    )
                if videoid == "telegram":
                    button = stream_markup(chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=config.TELEGRAM_AUDIO_URL
                        if str(streamtype) == "audio"
                        else config.TELEGRAM_VIDEO_URL,
                        caption=f"<b>✨ Started Streaming</b>\n\n<b>🎧 Track :</b> {title[:27]}\n<b>⏱️ Duration :</b> {check[0]['dur']} minutes\n<b>🥀 Requested by :</b> {user}",
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "tg"
                elif videoid == "soundcloud":
                    button = stream_markup(chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=config.SOUNCLOUD_IMG_URL,
                        caption=f"<b>✨ Started Streaming</b>\n\n<b>🎧 Track :</b> {title[:27]}\n<b>⏱️ Duration :</b> {check[0]['dur']} minutes\n<b>🥀 Requested by :</b> {user}",
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "tg"
                else:
                    img = await get_thumb(videoid)
                    button = stream_markup(chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=img,
                        caption=f"<b>✨ Started Streaming</b>\n\n<b>🎧 Track :</b> {title[:27]}\n<b>⏱️ Duration :</b> {check[0]['dur']} minutes\n<b>🥀 Requested by :</b> {user}",
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"

    async def ping(self):
        pings = []
        if config.STRING1 and self.one.is_running:
            pings.append(self.one.ping)
        if config.STRING2 and self.two.is_running:
            pings.append(self.two.ping)
        if config.STRING3 and self.three.is_running:
            pings.append(self.three.ping)
        if config.STRING4 and self.four.is_running:
            pings.append(self.four.ping)
        if config.STRING5 and self.five.is_running:
            pings.append(self.five.ping)
        
        if pings:
            return str(round(sum(pings) / len(pings), 3))
        return "N/A"

    async def start(self):
        LOGGER(__name__).info("Starting PyTgCalls Client...\n")
        if config.STRING1:
            await self.userbot1.start()
            await self.one.start()
        if config.STRING2:
            await self.userbot2.start()
            await self.two.start()
        if config.STRING3:
            await self.userbot3.start()
            await self.three.start()
        if config.STRING4:
            await self.userbot4.start()
            await self.four.start()
        if config.STRING5:
            await self.userbot5.start()
            await self.five.start()

    async def decorators(self):
        @self.one.on_kicked()
        @self.two.on_kicked()
        @self.three.on_kicked()
        @self.four.on_kicked()
        @self.five.on_kicked()
        @self.one.on_closed_voice_chat()
        @self.two.on_closed_voice_chat()
        @self.three.on_closed_voice_chat()
        @self.four.on_closed_voice_chat()
        @self.five.on_closed_voice_chat()
        @self.one.on_left()
        @self.two.on_left()
        @self.three.on_left()
        @self.four.on_left()
        @self.five.on_left()
        async def stream_services_handler(client, chat_id: int):
            await self.stop_stream(chat_id)

        @self.one.on_stream_end()
        @self.two.on_stream_end()
        @self.three.on_stream_end()
        @self.four.on_stream_end()
        @self.five.on_stream_end()
        async def stream_end_handler1(client, update: Update):
            if not isinstance(update, StreamAudioEnded):
                return
            await self.change_stream(client, update.chat_id)

Anony = Call()

