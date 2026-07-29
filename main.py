# WMark Bot v2.25.19 - Fixed CURRENT_COLOR + FFMPEG
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
import ffmpeg
from PIL import Image, ImageDraw, ImageFont

# ===== DEFAULT SETTINGS FIX =====
CURRENT_COLOR = (255, 255, 255) # White - yehi missing thi
CURRENT_SIZE = 15 # %
CURRENT_OPACITY = 100
WATERMARK_TEXT = "@bvsrv1"
FONT_PATH = "DejaVuSans.ttf"

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_PASSWORD = os.getenv("BOT_PASSWORD")
MAX_SIZE_MB = int(os.getenv("MAX_SIZE_MB", 180))

app = Client("wmark_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_state = {}

def add_watermark(input_path, output_path):
    font = ImageFont.truetype(FONT_PATH, 50)
    img = Image.new('RGBA', (1000, 200), (0,0,0,0))
    d = ImageDraw.Draw(img)
    d.text((10, 10), WATERMARK_TEXT, font=font, fill=CURRENT_COLOR + (CURRENT_OPACITY,))
    img.save("wm.png")
    
    (
        ffmpeg
       .input(input_path)
       .overlay(ffmpeg.input("wm.png"), x='W-w-10', y='H-h-10')
       .output(output_path, vcodec='libx264', acodec='copy')
       .run(overwrite_output=True)
    )
    os.remove("wm.png")

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply(f"**WMark Bot v2.25.19**\nLogin karo: `/login {BOT_PASSWORD}`")

@app.on_message(filters.command("login"))
async def login(client, message):
    if message.command[1] == BOT_PASSWORD:
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
        await message.reply_video(output_path)
        os.remove(file_path)
        os.remove(output_path)
    except Exception as e:
        await message.reply(f"❌ Failed: {e}")

app.run()