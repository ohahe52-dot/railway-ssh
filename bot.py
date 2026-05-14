# bot.py - Phiên bản hoàn chỉnh tích hợp Logging
import discord
import aiohttp
import os
import asyncio
import logging
from fastapi import FastAPI, Request
import uvicorn
import threading

# ============ CẤU HÌNH LOGGING ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"), # Ghi log vào file bot.log
        logging.StreamHandler()                           # Hiển thị log ra console
    ]
)
logger = logging.getLogger("DiscordProxy")

logger.info("🚀 Starting Discord Proxy Bot...")

# ============ DISCORD BOT ============
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

HUGGINGFACE_WEBHOOK_URL = os.getenv("HUGGINGFACE_WEBHOOK_URL", "")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

@bot.event
async def on_ready():
    logger.info(f"✅ Proxy Bot đã sẵn sàng: {bot.user}")
    logger.info(f"📊 Đang hoạt động trên {len(bot.guilds)} server")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Chỉ xử lý tin nhắn từ Channel ID cụ thể nếu CHANNEL_ID được cấu hình hợp lệ
    if CHANNEL_ID != 0 and message.channel.id != CHANNEL_ID:
        return

    logger.info(f"📩 Tin nhắn từ {message.author} tại kênh {message.channel.id}: {message.content[:50]}...")
    
    if not HUGGINGFACE_WEBHOOK_URL:
        logger.warning("⚠️ HUGGINGFACE_WEBHOOK_URL chưa được cấu hình")
        await message.channel.send("🤖 Bot đang được cấu hình, vui lòng thử lại sau!")
        return
    
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "content": message.content,
                "author": message.author.display_name,
                "channel_id": str(message.channel.id),
                "user_id": str(message.author.id)
            }
            async with session.post(HUGGINGFACE_WEBHOOK_URL, json=payload, timeout=10) as resp:
                logger.info(f"📤 Gửi sang HF, status: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Lỗi gửi sang HF: {e}", exc_info=True)
            await message.channel.send("⚠️ Lỗi kết nối đến AI server, vui lòng thử lại!")

# ============ FASTAPI SERVER ============
app = FastAPI()

@app.post("/send_message")
async def send_message(request: Request):
    try:
        data = await request.json()
        # Sử dụng CHANNEL_ID mặc định nếu API không truyền channel_id cụ thể
        target_channel_id = int(data.get("channel_id", CHANNEL_ID))
        content = data.get("content", "")
        
        if target_channel_id == 0:
            logger.warning("⚠️ Không tìm thấy target channel ID hợp lệ từ API hoặc cấu hình")
            return {"status": "error", "message": "Invalid Channel ID"}

        channel = bot.get_channel(target_channel_id)
        if channel:
            await channel.send(content)
            logger.info(f"✅ Đã gửi phản hồi đến kênh {target_channel_id}: {content[:50]}...")
            return {"status": "sent"}
        
        logger.warning(f"❌ Không tìm thấy kênh Discord với ID: {target_channel_id}")
        return {"status": "error", "message": "Channel not found"}
    except Exception as e:
        logger.error(f"❌ Lỗi xử lý API send_message: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.get("/health")
async def health():
    return {"status": "alive", "bot_ready": bot.is_ready()}

# ============ MAIN ============
def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8080, log_config=None) # Tắt log mặc định của uvicorn để tránh trùng lặp

def run_bot():
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN không được cấu hình!")
        logger.error("🔧 Hãy set biến môi trường DISCORD_TOKEN trên Railway")
        return
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.warning("⚠️ CẢNH BÁO: DISCORD_TOKEN chưa được cấu hình!")
        logger.warning("🔧 Vào Railway Dashboard → Variables → Thêm DISCORD_TOKEN")
    
    # Chạy API server
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    logger.info("✅ API server started on port 8080")
    
    # Chạy bot
    run_bot()
