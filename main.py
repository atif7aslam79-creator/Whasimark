import os
import re
import time
import asyncio
import uuid
import tempfile # FIX 1
import shutil
import shlex # FIX 2: special text ke liye
from telethon import TelegramClient, events, Button
import zipfile

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")

WATERMARK = os.environ.get("WATERMARK", "@bvsrv1")
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "1"))
MAX_SIZE_MB = 180

client = TelegramClient('bot_session', API_ID, API_HASH)

queue = asyncio.Queue()
processing = set()
semaphore = asyncio.Semaphore(MAX_CONCURRENT)
cancel_flags = {}
AUTHORIZED_USERS = set()
PENDING_STATES = {}
queue_messages = {}
ZIP_QUEUE = []
last_edit = {}

CURRENT_WATERMARK = WATERMARK
CURRENT_COLOR = "red@1"
DELETE_ORIGINAL = False
NAME_MODE = "water_id"
CUSTOM_PREFIX = "wm_"
WATERMARK_MODE = "bouncing"
ZIP_MODE = False
NO_WM_MODE = False
WM_PERCENT = 0.05

async def worker():
    while True:
        event, user_id = await queue.get()
        async with semaphore:
            if event.id in cancel_flags or user_id in cancel_flags:
                cancel_flags.pop(event.id, None)
                cancel_flags.pop(user_id, None)
                queue.task_done()
                continue
            processing.add(event.id)
            try:
                await process_video(event, user_id)
            except Exception as e:
                print(f"WORKER ERROR: {e}")
            finally:
                processing.discard(event.id)
                cancel_flags.pop(event.id, None)
                queue.task_done()

async def progress_callback(current, total, msg, action, event_id, user_id):
    if event_id in cancel_flags or user_id in cancel_flags:
        raise asyncio.CancelledError("Cancelled by user")
    percent = int(current * 100 / total)
    now = time.time()
    if (percent % 20 == 0 or percent == 100) and (now - last_edit.get(msg.id, 0) > 3):
        last_edit[msg.id] = now
        try: await msg.edit(f"{action} {percent}%")
        except: pass

async def process_video(event, user_id):
    global ZIP_QUEUE
    msg = None
    temp_dir = None # FIX 3
    try:
        # FIX 3: Har video ke liye alag folder
        temp_dir = tempfile.mkdtemp()
        unique_id = uuid.uuid4().hex

        q_pos = queue.qsize() + len(processing)
        msg = await client.send_message(user_id, f"⏳ **Queue #{q_pos}**")
        queue_messages[event.id] = msg.id

        file = f"{temp_dir}/input_{unique_id}.mp4"
        await event.download_media(file, progress_callback=lambda c, t: progress_callback(c, t, msg, "📥 Downloading", event.id, user_id))
        if event.id in cancel_flags or user_id in cancel_flags: raise asyncio.CancelledError("Cancelled")

        if NAME_MODE == "original":
            output = event.file.name if event.file and event.file.name else f"video_{unique_id}.mp4"
        elif NAME_MODE == "custom":
            output = f"{CUSTOM_PREFIX}{event.file.name}" if event.file and event.file.name else f"{CUSTOM_PREFIX}video_{unique_id}.mp4"
        else:
            output = f"water_{unique_id}.mp4"
        output = f"{temp_dir}/{output}" # output bhi temp me

        safe_watermark = shlex.quote(CURRENT_WATERMARK) # FIX 2

        original_size_mb = os.path.getsize(file) / (1024*1024)
        needs_compress = original_size_mb > 80

        if NO_WM_MODE:
            await msg.edit("📦 **No Watermark Mode**")
            shutil.copy(file, output)
        else:
            probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', file]
            probe = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await probe.communicate()
            if not stdout: raise Exception(f"FFprobe Error: {stderr.decode()}")
            w, h = map(int, stdout.decode().strip().split('x'))

            file_for_wm = file
            temp_file = None

            if needs_compress:
                await msg.edit(f"🗜️ **Step 1/2: Compressing to 720p...** `{original_size_mb:.1f}MB`")
                temp_file = f"{temp_dir}/temp_{unique_id}.mp4"
                # FIX 4: scale fix - width hamesha jora
                cmd1 = ['ffmpeg', '-xerror', '-threads', '1', '-i', file, '-vf', f"scale=trunc(iw/2)*2:720", '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-maxrate', '2M', '-bufsize', '4M', '-c:a', 'aac', '-b:a', '96k', temp_file, '-y']
                proc1 = await asyncio.create_subprocess_exec(*cmd1, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr1 = await proc1.communicate()
                if proc1.returncode != 0: raise Exception(f"FFmpeg Step 1 Error:\n{stderr1.decode()}") # FIX 5: Pura error
                file_for_wm = temp_file
                probe_cmd2 = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', temp_file]
                probe2 = await asyncio.create_subprocess_exec(*probe_cmd2, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout2, _ = await probe2.communicate()
                w, h = map(int, stdout2.decode().strip().split('x'))

            await msg.edit("🎬 **Step 2/2: Watermark laga rahe...**")
            dynamic_size = int(w * WM_PERCENT)
            final_size = max(20, min(150, dynamic_size))
            text_w = final_size * 0.5 * len(CURRENT_WATERMARK)
            margin = int(w * 0.02)
            max_x = max(margin, w - text_w - margin)
            max_y = max(margin, h - final_size - margin)

            if WATERMARK_MODE == "bouncing":
                speed_x = w / 10
                speed_y = h / 12
                x_formula = f"min(max({margin}\\,mod({speed_x}*t\\,{max_x}))\\,{max_x})"
                y_formula = f"min(max({margin}\\,mod({speed_y}*t\\,{max_y}))\\,{max_y})"
            else:
                x_formula = f"{margin}"
                y_formula = f"{margin}"

            # FIX 2: shlex.quote ki wajah se quotes nahi
            vf_filter = f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text={safe_watermark}:fontsize={final_size}:fontcolor={CURRENT_COLOR}:x={x_formula}:y={y_formula}"
            crf_val = '26' if needs_compress else '24'
            cmd2 = ['ffmpeg', '-xerror', '-threads', '1', '-i', file_for_wm, '-vf', vf_filter, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', crf_val, '-c:a', 'copy', output, '-y']
            proc2 = await asyncio.create_subprocess_exec(*cmd2, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr2 = await proc2.communicate()
            if proc2.returncode != 0: raise Exception(f"FFmpeg Step 2 Error:\n{stderr2.decode()}") # FIX 5: Pura error

        if ZIP_MODE:
            shutil.move(output, os.path.basename(output))
            ZIP_QUEUE.append(os.path.basename(output))
            await event.reply(f"📦 **Added to Zip Queue**\nTotal: `{len(ZIP_QUEUE)}`")
        else:
            if event.id in queue_messages: await client.delete_messages(user_id, queue_messages[event.id])
            final_size_mb = os.path.getsize(output) / (1024*1024)
            await client.send_file(event.chat_id, output, caption=f"✅ Done | Size: `{original_size_mb:.1f}MB` > `{final_size_mb:.1f}MB`", reply_to=event.id, force_document=True, progress_callback=lambda c, t: progress_callback(c, t, msg, "📤 Uploading", event.id, user_id))
            await msg.delete()
            
        if DELETE_ORIGINAL: await event.delete()

    except asyncio.CancelledError:
        if msg: await msg.edit("🚫 Cancelled by user")
    except Exception as e:
        if msg: await msg.edit(f"❌ Failed: {e}")
    finally:
        try:
            if temp_dir and os.path.exists(temp_dir): 
                shutil.rmtree(temp_dir) # FIX 3: pura folder saaf
        except: pass

# ===== BAQI SARA CODE SAME HAI =====
# Neeche wala sab copy kar lo apne purane code se
# Sirf start me version change kar dena
@client.on(events.NewMessage(pattern=r'^/start'))
async def start_handler(event):
    buttons = [
        [Button.inline('🔑 Bot Login', b'login'), Button.inline('🔒 Logout', b'logout')],
        [Button.inline('📊 Current Settings', b'current'), Button.inline('📖 Help', b'help')],
        [Button.inline('✏️ Set WM Text', b'set'), Button.inline('🎨 Set Color', b'color')],
        [Button.inline('📐 WM Size %', b'wmpercent'), Button.inline('📏 Set Limit', b'limit')],
        [Button.inline('🔄 WM Mode', b'wmmode'), Button.inline('🚫 No WM', b'nowm')],
        [Button.inline('🗑️ Delete Orig', b'delete'), Button.inline('📝 File Name', b'setname')],
        [Button.inline('📦 Zip Mode', b'zip'), Button.inline('⬇️ Create Zip', b'zipnow')],
        [Button.inline('❌ Cancel Queue', b'cancel_menu')]
    ]
    await event.reply('**WMark Bot v2.25.18**\nNeeche se setting select karo:', buttons=buttons)

# ... baqi sab handlers same ...
# main() me bhi version change kar dena
async def main():
    for _ in range(MAX_CONCURRENT): asyncio.create_task(worker())
    await client.start(bot_token=BOT_TOKEN)
    print("✅ Bot Online v2.25.18")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())