import os, tempfile, subprocess, yt_dlp, gzip, json
from io import BytesIO
from lottie.parsers.tgs import parse_tgs
from lottie.exporters.gif import export_gif
from config import logger

async def to_gif(webm=None, mp4=None, tgs=None):
    try:
        if webm or mp4:
            with tempfile.NamedTemporaryFile(suffix=('mp4' if mp4 else 'webm'), delete=False) as temp_video:
                temp_video.write((webm or mp4).getvalue())
                temp_video.flush()
                process = subprocess.run(["ffmpeg","-i",temp_video.name,"-an","-sn","-dn","-t","60","-filter_complex","[0:v]fps=15,scale=320:-1:flags=bilinear,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=2","-loop", "0","-f", "gif","pipe:1",], input=(webm or mp4).getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            result = BytesIO(process.stdout)
            result.seek(0)
            if os.path.exists(temp_video.name): os.remove(temp_video.name)
        if tgs:
            with gzip.GzipFile(fileobj=tgs) as gz: json_data = gz.read()
            animation = parse_tgs(BytesIO(json_data))
            result = BytesIO()
            export_gif(animation, result)
            result.seek(0)

        return result
    
    except subprocess.CalledProcessError as e: 
        logger.error(f"FFmpeg error: {e.stderr.decode()}")  # <-- Лог ошибки
    except Exception as e: 
        logger.error(e, exc_info=True)

async def to_tgs(json_file=None):
    try:
        if json_file:
            json_file = json.loads(json_file)
            result = BytesIO()
            with gzip.GzipFile(fileobj=result, mode="wb") as gz:
                gz.write(json.dumps(json_file).encode("utf-8"))
            result.seek(0)

        return result
    
    except Exception as e: 
        logger.error(e, exc_info=True)

async def to_mp3(url=None): 
    try:
        if url:
            process = subprocess.Popen(["ffmpeg","-i", url, "-f", "mp3", "-acodec", "libmp3lame", "-vn", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            result = process.stdout.read()

        return result
    
    except subprocess.CalledProcessError as e: 
        logger.error(f"FFmpeg error: {e.stderr.decode()}")  # <-- Лог ошибки
    except Exception as e: 
        logger.error(e, exc_info=True)
    

async def to_mp4(url_vk=None): 
    try:
        if url_vk:
            with yt_dlp.YoutubeDL({'outtmpl': 'video.mp4'}) as ydl:
                ydl.download([url_vk])
                with open("video.mp4", "rb") as f: result = f.read()
                if os.path.exists("video.mp4"): os.remove("video.mp4")

        return result
    
    except Exception as e: 
        if "This video is protected by privacy settings and isn't available for viewing" in str(e): logger.info(e)
        else: logger.error(e, exc_info=True)