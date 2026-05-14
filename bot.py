import discord
import aiohttp
import os
import asyncio
from fastapi import FastAPI, Request
import uvicorn
import threading

# ============ PHẦN 1: DISCORD BOT ============
intents = discord.Intents.default()
intents.message_content = True  # BẮT BUỘC - để đọc nội dung tin nhắn
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
    
    # Gửi tin nhắn sang Hugging Face để xử lý AI
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

# ============ PHẦN 2: FASTAPI SERVER (nhận phản hồi từ HF) ============
app = FastAPI()

@app.post("/send_message")
async def send_message(request: Request):
    """Endpoint để HF gửi phản hồi AI về"""
    data = await request.json()
    channel_id = int(data.get("channel_id"))
    content = data.get("content", "")
    
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(content)
        print(f"✅ Đã gửi phản hồi về Discord: {content[:50]}...")
        return {"status": "sent"}
    return {"status": "error", "message": "Channel not found"}

# ============ PHẦN 3: CHẠY CẢ 2 ============
def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8080)

def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN not set")
    bot.run(token)

if __name__ == "__main__":
    # Chạy API server trong thread riêng
    threading.Thread(target=run_api, daemon=True).start()
    # Chạy bot (blocking)
    run_bot()