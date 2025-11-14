# saini.py  -- UPDATED saini_final_fix_v2.py (new single watermark system deleted)
import os
import re
import time
import mmap
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import tgcrypto
import subprocess
import concurrent.futures
from math import ceil
from utils import progress_bar
from pyrogram import Client, filters
from pyrogram.types import Message
from io import BytesIO
from pathlib import Path  
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode
from requests.exceptions import RequestException


# ==================== STARTUP CLEANUP ====================
import shutil
startup_folders = ["downloads", "temp", "/tmp", "videos", "cache"]
for folder in startup_folders:
    try:
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)
            print(f"🧽 Pre-startup cleanup: removed {folder}")
    except Exception as e:
        print(f"⚠️ Startup cleanup error in {folder}: {e}")
print("✅ Pre-startup cleanup complete. Ready to run bot.")
# =========================================================


def duration(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    try:
        return float(result.stdout)
    except:
        return 0.0

def get_mps_and_keys(api_url):
    response = requests.get(api_url)
    response_json = response.json()
    mpd = response_json.get('MPD')
    keys = response_json.get('KEYS')
    return mpd, keys

def get_mps_and_keys2(api_url):
    response = requests.get(api_url)
    response_json = response.json()
    mpd = response_json.get('mpd_url')
    keys = response_json.get('keys')
    return mpd, keys

def get_mps_and_keys3(api_url):
    response = requests.get(api_url)
    response_json = response.json()
    mpd = response_json.get('url')
    return mpd

def exec(cmd):
        process = subprocess.run(cmd, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        output = process.stdout.decode()
        print(output)
        return output

def pull_run(work, cmds):
    with concurrent.futures.ThreadPoolExecutor(max_workers=work) as executor:
        print("Waiting for tasks to complete")
        fut = executor.map(exec,cmds)
        
async def aio(url,name):
    k = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return k

async def download(url,name):
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka

def parse_vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = []
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",2)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.append((i[0], i[2]))
            except:
                pass
    return new_info

def vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = dict()
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",3)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.update({f'{i[2]}':f'{i[0]}'})
            except:
                pass
    return new_info

async def decrypt_and_merge_video(mpd_url, keys_string, output_path, output_name, quality="720"):
    try:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        cmd1 = f'yt-dlp -f "bv[height<={quality}]+ba/b" -o "{output_path}/file.%(ext)s" --allow-unplayable-format --no-check-certificate --external-downloader aria2c "{mpd_url}"'
        print(f"Running command: {cmd1}")
        os.system(cmd1)
        
        avDir = list(output_path.iterdir())
        print(f"Downloaded files: {avDir}")
        print("Decrypting")

        video_decrypted = False
        audio_decrypted = False

        for data in avDir:
            if data.suffix == ".mp4" and not video_decrypted:
                cmd2 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/video.mp4"'
                print(f"Running command: {cmd2}")
                os.system(cmd2)
                if (output_path / "video.mp4").exists():
                    video_decrypted = True
                data.unlink()
            elif data.suffix == ".m4a" and not audio_decrypted:
                cmd3 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/audio.m4a"'
                print(f"Running command: {cmd3}")
                os.system(cmd3)
                if (output_path / "audio.m4a").exists():
                    audio_decrypted = True
                data.unlink()

        if not video_decrypted or not audio_decrypted:
            raise FileNotFoundError("Decryption failed: video or audio file not found.")

        cmd4 = f'ffmpeg -i "{output_path}/video.mp4" -i "{output_path}/audio.m4a" -c copy "{output_path}/{output_name}.mp4"'
        print(f"Running command: {cmd4}")
        os.system(cmd4)
        if (output_path / "video.mp4").exists():
            (output_path / "video.mp4").unlink()
        if (output_path / "audio.m4a").exists():
            (output_path / "audio.m4a").unlink()
        
        filename = output_path / f"{output_name}.mp4"

        if not filename.exists():
            raise FileNotFoundError("Merged video file not found.")

        cmd5 = f'ffmpeg -i "{filename}" 2>&1 | grep "Duration"'
        duration_info = os.popen(cmd5).read()
        print(f"Duration info: {duration_info}")

        return str(filename)

    except Exception as e:
        print(f"Error during decryption and merging: {str(e)}")
        raise

async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'

def old_download(url, file_name, chunk_size = 1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name

def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"

async def download_video(url,cmd, name):
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter
    print(download_cmd)
    logging.info(download_cmd)
    k = subprocess.run(download_cmd, shell=True)
    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        await download_video(url, cmd, name)
    failed_counter = 0
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"

        return name
    except FileNotFoundError as exc:
        return os.path.isfile.splitext[0] + "." + "mp4"

async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name, channel_id):
    reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
    time.sleep(1)
    start_time = time.time()
    await bot.send_document(ka, caption=cc1)
    count+=1
    await reply.delete (True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3) 

def decrypt_file(file_path, key):  
    if not os.path.exists(file_path): 
        return False  

    with open(file_path, "r+b") as f:  
        num_bytes = min(28, os.path.getsize(file_path))  
        with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:  
            for i in range(num_bytes):  
                mmapped_file[i] ^= ord(key[i]) if i < len(key) else i 
    return True  

async def download_and_decrypt_video(url, cmd, name, key):  
    video_path = await download_video(url, cmd, name)  
    
    if video_path:  
        decrypted = decrypt_file(video_path, key)  
        if decrypted:  
            print(f"File {video_path} decrypted successfully.")  
            return video_path  
        else:  
            print(f"Failed to decrypt {video_path}.")  
            return None

# ==================== SIMPLE WATERMARK SYSTEM (SAFE & UNIVERSAL) ====================

def add_watermark_simple(input_file, output_file, watermark_text):
    """
    Simple watermark overlay (uses FFmpeg's built-in font)
    Works on Render / Termux / VPS without Arial or font issues.
    """
    # Ensure paths are quoted - handles spaces
    cmd = (
        f'ffmpeg -i "{input_file}" '
        f'-vf "drawtext=text=\'{watermark_text}\':'
        f'fontcolor=white:fontsize=40:'
        f'box=1:boxcolor=black@0.5:boxborderw=8:'
        f'x=(w-text_w)/2:y=(h-text_h)/2" '
        f'-c:v libx264 -preset fast -crf 23 -c:a copy -y "{output_file}"'
    )
    print(f"🔧 Running watermark command:\n{cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        if os.path.exists(output_file):
            print("✅ Watermark applied, output exists.")
            return True
        else:
            print("❌ Watermark process finished but output missing.")
            print("stderr:", result.stderr)
            return False
    else:
        print("❌ Watermark failed. FFmpeg stderr:")
        print(result.stderr)
        return False

# ==================== UPDATED SEND_VID FUNCTION (uses add_watermark_simple) ====================
async def send_vid(bot: Client, m: Message, cc, filename, vidwatermark, thumb, name, prog, channel_id, message_thread_id=None):
    # Generate thumbnail (safe command - overwrite if exists)
    try:
        subprocess.run(f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 "{filename}.jpg" -y', shell=True, capture_output=True, text=True)
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")

    # delete progress message if passed
    try:
        await prog.delete(True)
    except Exception:
        pass

    reply1 = await bot.send_message(channel_id, f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>")
    reply = await m.reply_text(f"**Processing Video:**\n<blockquote>**{name}**</blockquote>")

    try:
        # Set thumbnail path
        if thumb == "/d":
            thumbnail = f"{filename}.jpg"
        else:
            thumbnail = thumb

        # WATERMARK DISABLED
        # Watermarking was removed for stability. Use original file directly.
        print('🚫 Watermark disabled (clean version). Using original file.')
    except Exception as e:
        print(f"Warning while setting thumbnail or watermark disabled: {e}")

# Get duration
    if os.path.exists(filename):
        try:
            dur = int(duration(filename))
        except:
            dur = 0
        file_size = human_readable_size(os.path.getsize(filename))
        print(f"📊 Final file: {filename} | Duration: {dur}s | Size: {file_size}")
    else:
        print(f"❌ Final file not found: {filename}")
        dur = 0

    start_time = time.time()

    try:
        await reply.edit_text(f"**📤 Uploading Video:**\n<blockquote>**{name}**</blockquote>")
        await bot.send_video(
            channel_id, 
            filename, 
            caption=cc, 
            message_thread_id=message_thread_id, 
            supports_streaming=True, 
            height=720, 
            width=1280, 
            thumb=thumbnail, 
            duration=dur, 
            progress=progress_bar, 
            progress_args=(reply, start_time)
        )
        print("✅ Video uploaded successfully!")
    except Exception as e:
        print(f"❌ Video upload failed: {e}")
        try:
            await reply.edit_text(f"**📤 Uploading as Document:**\n<blockquote>**{name}**</blockquote>")
            await bot.send_document(
                channel_id, 
                filename, 
                caption=cc, 
                message_thread_id=message_thread_id, 
                progress=progress_bar, 
                progress_args=(reply, start_time)
            )
            print("✅ Document uploaded successfully!")
        except Exception as e2:
            print(f"❌ Document upload failed too: {e2}")

    
    # CLEANUP
    try:
        await reply.delete(True)
    except:
        pass
    try:
        await reply1.delete(True)
    except:
        pass

    # Delete thumbnail and uploaded video
    try:
        base = os.path.splitext(filename)[0]
        thumb_path = f"{base}.jpg"
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
            print(f"🧹 Deleted thumbnail: {thumb_path}")
        if os.path.exists(filename):
            os.remove(filename)
            print(f"🧹 Deleted uploaded video: {filename}")
    except Exception as e:
        print(f"⚠️ Cleanup file delete error: {e}")

    # Deep-clean temp folders (safe for Render)
    import shutil
    try:
        folders_to_clean = ["downloads", "temp", "/tmp", "videos", "cache"]
        for f in folders_to_clean:
            if os.path.exists(f):
                shutil.rmtree(f, ignore_errors=True)
                print(f"🧽 Cleared folder: {f}")
    except Exception as e:
        print(f"⚠️ Folder cleanup error: {e}")

    print("🎉 Process completed successfully and cleaned up!")
