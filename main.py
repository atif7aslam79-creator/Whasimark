import subprocess # upar imports me ye add karna hai

def add_watermark(input_path, output_path):
    # Watermark image banao
    font = ImageFont.truetype(FONT_PATH, 60)
    img = Image.new('RGBA', (2000, 200), (0,0,0,0))
    d = ImageDraw.Draw(img)
    d.text((10, 10), WATERMARK_TEXT, font=font, fill=CURRENT_COLOR + (CURRENT_OPACITY,))
    img.save("wm.png")
    
    # FFMPEG command - Railway ke liye direct command
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-i', 'wm.png',
        '-filter_complex', '[0:v][1:v] overlay=W-w-20:H-h-20',
        '-c:a', 'copy',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-y', output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"ffmpeg stderr: {e.stderr}") # Asal error dikhayega
    finally:
        os.remove("wm.png")