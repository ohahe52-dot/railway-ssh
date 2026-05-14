# main.py - Đặt tên chính xác là main.py
import discord
import aiohttp
import os
import asyncio
from fastapi import FastAPI, Request
import uvicorn
import threading

# ============ DISCORD BOT ============
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

HUGGINGFACE_WEBHOOK_URL = os.getenv("HUGGINGFACE_WEBHOOK_URL", "")

@bot.event
async def on_ready():
    print(f"✅ Proxy Bot đã sẵn sàng: {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    print(f"📩 Tin nhắn từ {message.author}: {message.content[:50]}...")
    
    if not HUGGINGFACE_WEBHOOK_URL:
        print("⚠️ HUGGINGFACE_WEBHOOK_URL chưa được cấu hình")
        await message.channel.send("Bot đang được cấu hình, vui lòng thử lại sau!")
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
                print(f"📤 Gửi sang HF, status: {resp.status}")
        except Exception as e:
            print(f"❌ Lỗi gửi sang HF: {e}")
            await message.channel.send("⚠️ Lỗi kết nối đến AI server, vui lòng thử lại!")

# ============ FASTAPI SERVER ============
app = FastAPI()

@app.post("/send_message")
async def send_message(request: Request):
    data = await request.json()
    channel_id = int(data.get("channel_id"))
    content = data.get("content", "")
    
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(content)
        print(f"✅ Đã gửi phản hồi: {content[:50]}...")
        return {"status": "sent"}
    return {"status": "error", "message": "Channel not found"}

@app.get("/health")
async def health():
    return {"status": "alive", "bot_ready": bot.is_ready()}

# ============ MAIN ============
def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8080)

def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN không được cấu hình!")
        return
    bot.run(token)

if __name__ == "__main__":
    print("🚀 Starting Discord Proxy Bot...")
    
    # Chạy API server
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    print("✅ API server started on port 8080")
    
    # Chạy bot
    run_bot()
