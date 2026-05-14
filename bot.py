"""
bot.py — Railway
Chỉ chạy Discord bot.
Nhận tin nhắn từ Discord → gọi HF Space /chat → trả lời lại Discord.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import aiohttp
import discord
from discord.ext import commands

# ─────────────────────────────────────────────────────────
# Config từ environment variables
# ─────────────────────────────────────────────────────────
DISCORD_TOKEN    = os.environ["DISCORD_TOKEN"]
HF_SPACE_URL     = os.environ.get("HF_SPACE_URL", "").rstrip("/")
# Ví dụ: https://zxccxc-BotRobin.hf.space
CHANNEL_ID       = os.environ.get("CHANNEL_ID", "")          # Để trống = mọi kênh
COMMAND_PREFIX   = os.environ.get("COMMAND_PREFIX", "!")

if not HF_SPACE_URL:
    print("❌ Thiếu HF_SPACE_URL! Set trong Railway Variables.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────
# Keep HF Space alive — ping mỗi 10 phút
# ─────────────────────────────────────────────────────────
async def keep_hf_alive():
    await asyncio.sleep(60)  # Chờ 1 phút sau khi bot start
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{HF_SPACE_URL}/health",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"💓 HF Space alive: {resp.status}")
                    else:
                        logger.warning(f"⚠️ HF Space ping status: {resp.status}")
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"⚠️ HF ping - Cannot connect: {e}")
            logger.warning(f"   Kiểm tra HF_SPACE_URL = {HF_SPACE_URL}")
        except asyncio.TimeoutError:
            logger.warning("⚠️ HF ping - Timeout (HF Space đang cold start, bình thường)")
        except Exception as e:
            logger.warning(f"⚠️ HF ping - {type(e).__name__}: {e}")
        await asyncio.sleep(600)  # 10 phút


# ─────────────────────────────────────────────────────────
# Gọi HF Space để xử lý AI
# ─────────────────────────────────────────────────────────
async def call_hf_chat(content: str, author: str, channel_id: str, user_id: str) -> str:
    """
    Gọi HF Space /chat và trả về câu trả lời.
    Tự retry nếu HF Space đang cold start.
    """
    payload = {
        "content": content,
        "author": author,
        "channel_id": channel_id,
        "user_id": user_id,
    }

    timeout = aiohttp.ClientTimeout(total=90)  # HF cold start có thể mất ~60s

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{HF_SPACE_URL}/chat", json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("reply", "❌ Không có phản hồi từ AI.")
                    elif resp.status == 503:
                        # HF Space đang khởi động
                        logger.warning(f"HF Space 503, retry {attempt+1}/3...")
                        await asyncio.sleep(10)
                        continue
                    else:
                        text = await resp.text()
                        logger.error(f"HF Space returned {resp.status}: {text[:100]}")
                        return f"❌ AI server lỗi ({resp.status}), thử lại sau!"

        except asyncio.TimeoutError:
            logger.warning(f"Timeout attempt {attempt+1}/3")
            if attempt == 2:
                return "⏳ AI đang bận hoặc đang khởi động, thử lại sau 30 giây nhé!"
            await asyncio.sleep(5)

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Cannot connect to HF Space: {e}")
            return f"❌ Không kết nối được đến AI server. Kiểm tra HF_SPACE_URL."

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return f"❌ Lỗi: {str(e)}"

    return "❌ Thử 3 lần đều thất bại, vui lòng thử lại sau!"


# ─────────────────────────────────────────────────────────
# Events
# ─────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f"✅ Bot đã online: {bot.user} ({len(bot.guilds)} server)")
    logger.info(f"🔗 HF Space URL: {HF_SPACE_URL}")
    asyncio.create_task(keep_hf_alive())


@bot.event
async def on_resumed():
    logger.info("🔄 Bot reconnected!")


@bot.event
async def on_disconnect():
    logger.warning("⚠️ Bot mất kết nối, đang reconnect...")


@bot.event
async def on_message(message: discord.Message):
    # Bỏ qua tin của bot
    if message.author.bot:
        return

    # Xử lý commands trước
    await bot.process_commands(message)

    # Bỏ qua nếu là command
    if message.content.startswith(COMMAND_PREFIX):
        return

    # Lọc theo kênh nếu có cấu hình
    if CHANNEL_ID and str(message.channel.id) != CHANNEL_ID:
        return

    # Bỏ qua tin quá ngắn
    if len(message.content.strip()) < 2:
        return

    logger.info(f"📩 [{message.author.display_name}] #{message.channel}: {message.content[:60]}")

    # Hiện "đang gõ..." trong lúc chờ AI
    async with message.channel.typing():
        reply = await call_hf_chat(
            content=message.content,
            author=message.author.display_name,
            channel_id=str(message.channel.id),
            user_id=str(message.author.id),
        )

    # Tách tin dài > 2000 ký tự (giới hạn Discord)
    if len(reply) <= 2000:
        await message.reply(reply)
    else:
        chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                await message.reply(chunk)
            else:
                await message.channel.send(chunk)


# ─────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────
@bot.command(name="health")
async def cmd_health(ctx: commands.Context):
    """Kiểm tra trạng thái bot và HF Space"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(f"{HF_SPACE_URL}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await ctx.reply(f"✅ Bot: OK | HF Space: OK\n```json\n{data}\n```")
                else:
                    await ctx.reply(f"⚠️ Bot: OK | HF Space: {resp.status}")
    except Exception as e:
        await ctx.reply(f"✅ Bot: OK | HF Space: ❌ {e}")


@bot.command(name="ping")
async def cmd_ping(ctx: commands.Context):
    latency = round(bot.latency * 1000)
    await ctx.reply(f"🏓 Pong! `{latency}ms`")


# ─────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────
async def main():
    logger.info("🚀 Starting Discord Proxy Bot...")
    logger.info(f"HF Space: {HF_SPACE_URL}")

    async with bot:
        await bot.start(DISCORD_TOKEN, reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except discord.LoginFailure:
        logger.error("❌ DISCORD_TOKEN không hợp lệ!")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
