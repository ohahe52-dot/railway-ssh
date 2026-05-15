"""
bot.py — Railway
Bản nâng cấp STREAMING từ file gốc của bạn.
Giữ nguyên: Xử lý Attachment chi tiết, Reconnect, Logging, Keep-alive.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import sys
import time
import io
import re

import aiohttp
import discord
from discord.ext import commands

# ─────────────────────────────────────────────────────────
# Config từ environment variables
# ─────────────────────────────────────────────────────────
DISCORD_TOKEN    = os.environ["DISCORD_TOKEN"]
HF_SPACE_URL     = os.environ.get("HF_SPACE_URL", "").rstrip("/")
CHANNEL_ID       = os.environ.get("CHANNEL_ID", "")          
COMMAND_PREFIX   = os.environ.get("COMMAND_PREFIX", "!")

if not HF_SPACE_URL:
    print("❌ Thiếu HF_SPACE_URL! Set trong Railway Variables.")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# Discord Bot
# ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

def _guess_attachment_type(attachment: discord.Attachment) -> str | None:
    return attachment.content_type or mimetypes.guess_type(attachment.filename or "")[0]

def _build_attachment_payload(attachments: list[discord.Attachment]) -> list[dict]:
    payload = []
    for item in attachments:
        try:
            is_spoiler = item.is_spoiler()
        except Exception:
            is_spoiler = False

        payload.append({
            "id": str(item.id),
            "url": item.url,
            "proxy_url": item.proxy_url,
            "filename": item.filename,
            "content_type": _guess_attachment_type(item),
            "size": int(item.size or 0),
            "width": getattr(item, "width", None),
            "height": getattr(item, "height", None),
            "description": getattr(item, "description", None),
            "is_spoiler": is_spoiler,
        })
    return payload

async def download_file(url: str) -> discord.File | None:
    """Tải file từ link để gửi ngược lại Discord (Dành cho ảnh AI trả về)"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    fname = url.split("/")[-1].split("?")[0] or "result.png"
                    return discord.File(io.BytesIO(data), filename=fname)
    except: return None

# ─────────────────────────────────────────────────────────
# Keep HF Space alive
# ─────────────────────────────────────────────────────────
async def keep_hf_alive():
    await asyncio.sleep(60)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{HF_SPACE_URL}/health", timeout=30) as resp:
                    if resp.status == 200:
                        logger.info(f"💓 HF Space alive: {resp.status}")
        except Exception as e:
            logger.warning(f"⚠️ HF ping error: {e}")
        await asyncio.sleep(600)

# ─────────────────────────────────────────────────────────
# Xử lý Chat Stream (Nâng cấp từ call_hf_chat)
# ─────────────────────────────────────────────────────────
async def call_hf_chat_stream(
    content: str, author: str, channel_id: str, user_id: str,
    message: discord.Message, attachments: list[dict] | None = None,
    guild_id: str | None = None,
):
    payload = {
        "content": content, "author": author, "channel_id": channel_id,
        "user_id": user_id, "guild_id": guild_id or "", "attachments": attachments or [],
    }

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
                async with session.post(f"{HF_SPACE_URL}/chat-stream", json=payload) as resp:
                    if resp.status == 503:
                        logger.warning(f"HFS 503, retry {attempt+1}/3...")
                        await asyncio.sleep(10); continue
                    
                    if resp.status != 200:
                        err = await resp.text()
                        await message.reply(f"❌ Lỗi ({resp.status}): {err[:100]}")
                        return

                    # Bắt đầu hứng Stream
                    reply_msg = await message.reply("⏳ *Đang kết nối bộ não Robin...*")
                    full_text = ""
                    last_update = time.time()
                    
                    async for chunk in resp.content.iter_any():
                        token = chunk.decode("utf-8", errors="ignore")
                        full_text += token
                        
                        # Edit tin nhắn mỗi 0.6s để mượt và tránh bóp băng thông
                        if time.time() - last_update > 0.6 and full_text.strip():
                            display = full_text[-1990:] if len(full_text) > 1990 else full_text
                            await reply_msg.edit(content=display + " ▌")
                            last_update = time.time()

                    # --- XỬ LÝ ẢNH TRẢ VỀ (NẾU CÓ) ---
                    # Tìm link ảnh trong full_text để gửi đính kèm
                    img_urls = re.findall(r'(https?://\S+\.(?:png|jpg|jpeg|gif|webp))', full_text)
                    files = []
                    if img_urls:
                        for url in img_urls[:2]: # Tải tối đa 2 ảnh
                            f = await download_file(url)
                            if f: files.append(f)

                    # Hoàn tất tin nhắn
                    if len(full_text) <= 2000:
                        await reply_msg.edit(content=full_text, attachments=files)
                    else:
                        await reply_msg.edit(content=full_text[:1990], attachments=files)
                        for i in range(1990, len(full_text), 1990):
                            await message.channel.send(full_text[i:i+1990])
                    return

        except Exception as e:
            logger.error(f"Error: {e}")
            if attempt == 2: await message.reply("❌ AI server không phản hồi.")

# ─────────────────────────────────────────────────────────
# Events & Commands (GIỮ NGUYÊN GỐC)
# ─────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f"✅ Bot Online: {bot.user}")
    asyncio.create_task(keep_hf_alive())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.content.startswith(COMMAND_PREFIX):
        return
    if CHANNEL_ID and str(message.channel.id) != CHANNEL_ID:
        return

    att_payload = _build_attachment_payload(list(message.attachments))
    if len(message.content.strip()) < 2 and not att_payload:
        return

    logger.info(f"📩 [{message.author.display_name}]: {message.content[:60]}")

    async with message.channel.typing():
        # Dùng task để không làm nghẽn bot
        asyncio.create_task(call_hf_chat_stream(
            content=message.content, author=message.author.display_name,
            channel_id=str(message.channel.id), user_id=str(message.author.id),
            message=message, attachments=att_payload,
            guild_id=str(message.guild.id) if message.guild else ""
        ))

@bot.command(name="ping")
async def cmd_ping(ctx):
    await ctx.reply(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

async def main():
    async with bot: await bot.start(DISCORD_TOKEN, reconnect=True)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
