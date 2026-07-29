# WMark Bot v2.25.20 - Fixed FFMPEG + COLOR
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import ffmpeg
from PIL import Image, ImageDraw, ImageFont

# ===== DEFAULT SETTINGS =====
CURRENT_COLOR = (255, 255, 255) # White
CURRENT_SIZE = 15 
CURRENT_OPACITY = 100
WATERMARK_TEXT = os.getenv("WATERMARK", "@bvsrv1")
FONT_PATH = "DejaVuSans.ttf"

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_PASSWORD = os.getenv("BOT_PASSWORD")

app = Client("wmark_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_state = {}

def add_watermark(input_path, output_path):
    # Watermark image banao
    font = ImageFont.truetype(FONT_PATH, 60)
    img = Image.new('RGBA', (2000, 200), (0,0,0,0))
    d = ImageDraw.Draw(img)
    d.text((10, 10), WATERMARK_TEXT, font=font, fill=CURRENT_COLOR + (CURRENT_OPACITY,))
    img.save("wm.png")
    
    # FFMPEG se overlay karo - Railway ke liye fix
    try:
        stream = ffmpeg.input(input_path)
        watermark = ffmpeg.input("wm.png")
        stream = ffmpeg.overlay(stream, watermark, x='W-w-20', y='H-h-20')
        stream = ffmpeg.output(stream, output_path, vcodec='libx264', acodec='aac')
        ffmpeg.run(stream, overwrite_output=True, cmd='ffmpeg')
    finally:
        os.remove("wm.png")

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply(f"**WMark Bot v2.25.20**\nLogin karo: `/login {BOT_PASSWORD}`")

@app.on_message(filters.command("login"))
async def login(client, message):
    if len(message.command) > 1 and message.command[1] == BOT_PASSWORD:
        user_state[message.from_user.id] = "logged_in"
        await message.reply("✅ Login Success!")
    else:
        await message.reply("❌ Wrong Password")

@app.on_message(filters.video | filters.document)
async def handle_video(client, message: Message):
    if user_state.get(message.from_user.id)!= "logged_in":
        return await message.reply("Pehle /login karo")
    
    msg = await message.reply("Downloading...")
    file_path = await message.download()
    await msg.edit("Processing watermark...")
    
    try:
        output_path = "output.mp4"
        add_watermark(file_path, output_path)
        await message.reply_video(output_path, caption="✅ Done")
        os.remove(file_path)
        os.remove(output_path)
    except Exception as e:
        await message.reply(f"❌ Failed: {e}")

app.run()