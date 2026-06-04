import asyncio
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse

import edge_tts
import requests
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

ROOT = Path(".").resolve()
INPUT_DIR = ROOT / "input"
ASSETS_DIR = ROOT / "assets"
AUDIO_DIR = ROOT / "audio"
TEMP_DIR = ROOT / "temp"
OUTPUT_DIR = ROOT / "output"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

DEFAULT_SCENE_DURATIONS = [3, 5, 12, 13, 10, 7]
LANGUAGE_MAP = {
    "english": {
        "code": "en",
        "voice_male": "en-US-GuyNeural",
        "voice_female": "en-US-JennyNeural",
    },
    "indonesian": {
        "code": "id",
        "voice_male": "id-ID-ArdiNeural",
        "voice_female": "id-ID-GadisNeural",
    },
    "turkish": {
        "code": "tr",
        "voice_male": "tr-TR-AhmetNeural",
        "voice_female": "tr-TR-EmelNeural",
    },
    "spanish": {
        "code": "es",
        "voice_male": "es-ES-AlvaroNeural",
        "voice_female": "es-ES-ElviraNeural",
    },
    "portuguese": {
        "code": "pt",
        "voice_male": "pt-BR-AntonioNeural",
        "voice_female": "pt-BR-FranciscaNeural",
    },
    "french": {
        "code": "fr",
        "voice_male": "fr-FR-HenriNeural",
        "voice_female": "fr-FR-DeniseNeural",
    },
    "german": {
        "code": "de",
        "voice_male": "de-DE-ConradNeural",
        "voice_female": "de-DE-KatjaNeural",
    },
    "italian": {
        "code": "it",
        "voice_male": "it-IT-DiegoNeural",
        "voice_female": "it-IT-ElsaNeural",
    },
    "dutch": {
        "code": "nl",
        "voice_male": "nl-NL-MaartenNeural",
        "voice_female": "nl-NL-ColetteNeural",
    },
    "russian": {
        "code": "ru",
        "voice_male": "ru-RU-DmitryNeural",
        "voice_female": "ru-RU-SvetlanaNeural",
    },
    "arabic": {
        "code": "ar",
        "voice_male": "ar-SA-HamedNeural",
        "voice_female": "ar-SA-ZariyahNeural",
    },
    "hindi": {
        "code": "hi",
        "voice_male": "hi-IN-MadhurNeural",
        "voice_female": "hi-IN-SwaraNeural",
    },
    "japanese": {
        "code": "ja",
        "voice_male": "ja-JP-KeitaNeural",
        "voice_female": "ja-JP-NanamiNeural",
    },
    "korean": {
        "code": "ko",
        "voice_male": "ko-KR-InJoonNeural",
        "voice_female": "ko-KR-SunHiNeural",
    },
    "chinese": {
        "code": "zh-CN",
        "voice_male": "zh-CN-YunxiNeural",
        "voice_female": "zh-CN-XiaoxiaoNeural",
    },
    "vietnamese": {
        "code": "vi",
        "voice_male": "vi-VN-NamMinhNeural",
        "voice_female": "vi-VN-HoaiMyNeural",
    },
    "thai": {
        "code": "th",
        "voice_male": "th-TH-NiwatNeural",
        "voice_female": "th-TH-PremwadeeNeural",
    },
    "malay": {
        "code": "ms",
        "voice_male": "ms-MY-OsmanNeural",
        "voice_female": "ms-MY-YasminNeural",
    },
    "filipino": {
        "code": "tl",
        "voice_male": "fil-PH-AngeloNeural",
        "voice_female": "fil-PH-BlessicaNeural",
    },
    "polish": {
        "code": "pl",
        "voice_male": "pl-PL-MarekNeural",
        "voice_female": "pl-PL-ZofiaNeural",
    },
}

INTONATION_MAP = {
    "calm explainer": {
        "rate": "+0%",
        "pitch": "+0Hz",
        "gender": "male",
    },
    "energetic shorts": {
        "rate": "+13%",
        "pitch": "+4Hz",
        "gender": "male",
    },
    "news reporter": {
        "rate": "+8%",
        "pitch": "+2Hz",
        "gender": "male",
    },
    "mystery voice": {
        "rate": "-6%",
        "pitch": "-4Hz",
        "gender": "male",
    },
    "friendly female": {
        "rate": "+5%",
        "pitch": "+3Hz",
        "gender": "female",
    },
}

def ensure_dirs():
    for folder in [INPUT_DIR, ASSETS_DIR, AUDIO_DIR, TEMP_DIR, OUTPUT_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


def run(cmd, label):
    print("\n====================================================")
    print("STEP:", label)
    print("====================================================")
    print(" ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")
    return result.stdout


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def normalize_language(value):
    text = clean_text(value).lower()

    aliases = {
        "global language": "english",
        "en": "english",
        "id": "indonesian",
        "indonesia": "indonesian",
        "bahasa indonesia": "indonesian",
        "turkiye": "turkish",
        "turkish / türkiye": "turkish",
        "turkish / turkiye": "turkish",
        "tr": "turkish",
        "es": "spanish",
        "pt": "portuguese",
        "fr": "french",
        "de": "german",
        "it": "italian",
        "nl": "dutch",
        "ru": "russian",
        "ar": "arabic",
        "hi": "hindi",
        "ja": "japanese",
        "ko": "korean",
        "zh": "chinese",
        "zh-cn": "chinese",
        "vi": "vietnamese",
        "th": "thai",
        "ms": "malay",
        "tl": "filipino",
        "fil": "filipino",
        "pl": "polish",
    }

    text = aliases.get(text, text)

    if text not in LANGUAGE_MAP:
        return "english"

    return text


def normalize_intonation(value):
    text = clean_text(value).lower()

    aliases = {
        "calm": "calm explainer",
        "calm explainer": "calm explainer",
        "energetic": "energetic shorts",
        "energetic shorts": "energetic shorts",
        "news": "news reporter",
        "news reporter": "news reporter",
        "mystery": "mystery voice",
        "mystery voice": "mystery voice",
        "friendly female": "friendly female",
        "female": "friendly female",
    }

    text = aliases.get(text, text)

    if text not in INTONATION_MAP:
        return "calm explainer"

    return text


def get_voice_settings(language_value, intonation_value):
    language = normalize_language(language_value)
    intonation = normalize_intonation(intonation_value)

    lang_data = LANGUAGE_MAP[language]
    tone_data = INTONATION_MAP[intonation]

    voice_key = "voice_female" if tone_data.get("gender") == "female" else "voice_male"

    return {
        "language": language,
        "target_code": lang_data["code"],
        "voice": lang_data.get(voice_key) or lang_data["voice_male"],
        "rate": tone_data["rate"],
        "pitch": tone_data["pitch"],
        "intonation": intonation,
    }


def translate_for_language(text, target_code):
    text = clean_text(text)

    if not text:
        return text

    if target_code == "en":
        return text

    try:
        translated = GoogleTranslator(source="auto", target=target_code).translate(text)
        return clean_text(translated) or text
    except Exception as error:
        print("Translation fallback:", error)
        return text
        
def short_text(value, limit=900):
    text = clean_text(value)
    return text[:limit].rstrip()


def safe_filename(value, fallback="file"):
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", clean_text(value))
    text = text.strip("_")
    return text[:80] or fallback


def parse_duration(value, fallback):
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    text = clean_text(value)
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        return max(1.0, float(match.group(1)))
    return float(fallback)


def ffprobe_duration(path):
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        )
        value = float(output.strip())
        return value if value > 0 else 0
    except Exception:
        return 0


def extract_google_drive_id(url):
    url = clean_text(url)
    match = re.search(r"/file/d/([^/]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([^&]+)", url)
    if match:
        return match.group(1)
    return url


def download_gameplay(url, index):
    file_id = extract_google_drive_id(url)
    output = INPUT_DIR / f"gameplay_{index:02d}.mp4"
    run(["gdown", f"https://drive.google.com/uc?id={file_id}", "-O", str(output)], f"Download gameplay {index}")
    if not output.exists() or output.stat().st_size < 100_000:
        raise RuntimeError(f"Gameplay download invalid: {output}")
    return output


def pick_gameplay(gameplays, scene_index):
    if not gameplays:
        raise RuntimeError("No gameplay files available")
    return gameplays[scene_index % len(gameplays)]


def random_seek(video_path, duration, seed):
    total = ffprobe_duration(video_path)
    if total <= duration + 2:
        return 0
    random.seed(seed)
    return round(random.uniform(0, max(0, total - duration - 1)), 2)


def possible_image_url(value):
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value.startswith("http"):
        return False
    lower = value.lower()
    return (
        any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp"])
        or "images" in lower
        or "thumbnail" in lower
        or "ytimg" in lower
        or "rbxcdn" in lower
        or "roblox" in lower
    )


def collect_urls_deep(obj, limit=60):
    found = []

    def walk(value):
        if len(found) >= limit:
            return
        if isinstance(value, dict):
            for key, val in value.items():
                key_l = str(key).lower()
                if isinstance(val, str) and (
                    "image" in key_l
                    or "thumbnail" in key_l
                    or "poster" in key_l
                    or "url" in key_l
                    or "src" in key_l
                ):
                    if possible_image_url(val):
                        found.append(val.strip())
                else:
                    walk(val)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and possible_image_url(value):
            found.append(value.strip())

    walk(obj)

    unique = []
    seen = set()
    for url in found:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique[:limit]


def download_image(url, output):
    headers = {
        "User-Agent": "Mozilla/5.0 Roblox Shorts Render Worker",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code >= 400 or len(response.content) < 2000:
            return False
        output.write_bytes(response.content)

        with Image.open(output) as im:
            im.verify()

        return True
    except Exception:
        try:
            output.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for item in candidates:
        if os.path.exists(item):
            return ImageFont.truetype(item, size)
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = clean_text(text).split()
    lines = []
    current = ""

    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def make_text_card(path, title, body, topic, scene_index):
    img = Image.new("RGB", (900, 900), (12, 20, 35))
    draw = ImageDraw.Draw(img)

    accent = (0, 210, 125)
    white = (245, 248, 250)
    muted = (190, 210, 220)

    title_font = get_font(54, bold=True)
    body_font = get_font(36, bold=False)
    small_font = get_font(28, bold=True)

    draw.rounded_rectangle((28, 28, 872, 872), radius=36, outline=accent, width=6)
    draw.text((60, 64), f"SCENE {scene_index}", font=small_font, fill=accent)

    y = 130
    for line in wrap_text(draw, title, title_font, 780)[:4]:
        draw.text((60, y), line, font=title_font, fill=white)
        y += 66

    y += 24
    for line in wrap_text(draw, body, body_font, 780)[:8]:
        draw.text((60, y), line, font=body_font, fill=muted)
        y += 48

    footer = short_text(topic, 90)
    draw.text((60, 810), footer, font=small_font, fill=accent)

    img.save(path, "PNG")
    return path


def make_cta_card(path, topic):
    img = Image.new("RGB", (900, 900), (4, 24, 18))
    draw = ImageDraw.Draw(img)

    white = (250, 255, 252)
    accent = (0, 230, 135)
    dark = (10, 50, 38)

    title_font = get_font(68, bold=True)
    body_font = get_font(42, bold=True)

    draw.rounded_rectangle((26, 26, 874, 874), radius=42, outline=accent, width=8)
    draw.rounded_rectangle((70, 110, 830, 285), radius=34, fill=dark)
    draw.text((110, 155), "WHAT DO YOU THINK?", font=body_font, fill=white)

    y = 360
    lines = [
        "Comment your answer.",
        "Like if this helped.",
        "Follow for more Roblox updates.",
    ]
    for line in lines:
        draw.text((90, y), line, font=body_font, fill=accent if "Follow" in line else white)
        y += 88

    topic_lines = wrap_text(draw, short_text(topic, 120), get_font(28, bold=False), 740)
    y = 735
    for line in topic_lines[:3]:
        draw.text((90, y), line, font=get_font(28, bold=False), fill=(180, 220, 205))
        y += 38

    img.save(path, "PNG")
    return path


def prepare_scene_images(job, scenes):
    global_urls = []
    global_urls.extend(collect_urls_deep(job.get("sourceResults", []), limit=40))
    global_urls.extend(collect_urls_deep(job.get("research", {}), limit=40))

    prepared = []
    url_cursor = 0

    for idx, scene in enumerate(scenes, start=1):
        scene_urls = collect_urls_deep(scene, limit=20)

        while len(scene_urls) < 2 and url_cursor < len(global_urls):
            scene_urls.append(global_urls[url_cursor])
            url_cursor += 1

        scene_files = []
        for url in scene_urls[:3]:
            digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
            out = ASSETS_DIR / f"scene_{idx:02d}_{digest}.jpg"
            if download_image(url, out):
                scene_files.append(out)

        if not scene_files:
            card = ASSETS_DIR / f"scene_{idx:02d}_source_card.png"
            if idx == len(scenes):
                make_cta_card(card, job.get("topic", "Roblox update"))
            else:
                make_text_card(
                    card,
                    scene.get("title") or f"Scene {idx}",
                    scene.get("voiceOver") or scene.get("text") or job.get("topic", ""),
                    job.get("topic", "Roblox update"),
                    idx,
                )
            scene_files.append(card)

        prepared.append(scene_files)

    return prepared


def normalize_scenes(job):
    raw_scenes = job.get("scenes") if isinstance(job.get("scenes"), list) else []
    subtitles = job.get("subtitles") if isinstance(job.get("subtitles"), list) else []

    if not raw_scenes:
        topic = clean_text(job.get("topic")) or "Roblox update"
        raw_scenes = [
            {"id": 1, "title": "STRONG HOOK", "voiceOver": f"Do not skip this Roblox update. {topic} could affect more players than it seems."},
            {"id": 2, "title": "SOURCE CONTEXT", "voiceOver": f"This topic is connected to {topic}, and the source needs to be checked before calling it official."},
            {"id": 3, "title": "MAIN FACT", "voiceOver": f"The main point is about {topic}. Here is what Roblox players should know."},
            {"id": 4, "title": "EXTRA FACT", "voiceOver": f"This can affect updates, creators, items, and player reactions inside Roblox."},
            {"id": 5, "title": "TWIST", "voiceOver": f"Community buzz can make a topic look huge, but source-backed context still matters."},
            {"id": 6, "title": "QUESTION + CTA", "voiceOver": f"Do you think this Roblox update is a big deal? Comment your answer, like this video, and follow for more Roblox updates."},
        ]

    scenes = []
    for i, scene in enumerate(raw_scenes[:6]):
        subtitle = subtitles[i] if i < len(subtitles) and isinstance(subtitles[i], dict) else {}
        voice = (
            clean_text(scene.get("voiceOver"))
            or clean_text(scene.get("voiceover"))
            or clean_text(scene.get("text"))
            or clean_text(scene.get("subtitle"))
            or clean_text(subtitle.get("text"))
            or clean_text(job.get("topic"))
        )

        if i == 0 and not voice.lower().startswith(("do not skip", "stop", "wait", "this")):
            voice = "Do not skip this Roblox update. " + voice

        if i == 5 and "comment" not in voice.lower():
            voice = voice + " Comment your answer, like if this helped, and follow for more Roblox updates."

        duration = parse_duration(
            scene.get("duration") or scene.get("sceneDuration") or scene.get("time") or scene.get("range"),
            DEFAULT_SCENE_DURATIONS[i] if i < len(DEFAULT_SCENE_DURATIONS) else 8,
        )

        scenes.append({
            **scene,
            "id": scene.get("id") or scene.get("scene") or i + 1,
            "title": clean_text(scene.get("title")) or f"SCENE {i + 1}",
            "voiceOver": short_text(voice, 520),
            "duration": duration,
        })

    return scenes


async def generate_tts(text, out_path, voice="en-US-GuyNeural", rate="+0%", pitch="+0Hz"):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError(f"TTS failed: {out_path}")


def make_subtitle_overlay(path, scene_title, text):
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    title_font = get_font(42, bold=True)
    body_font = get_font(48, bold=True)

    panel_h = 360
    y0 = HEIGHT - panel_h - 80
    draw.rounded_rectangle((64, y0, WIDTH - 64, y0 + panel_h), radius=34, fill=(0, 0, 0, 165))

    draw.text((100, y0 + 34), short_text(scene_title.upper(), 42), font=title_font, fill=(0, 235, 135, 255))

    y = y0 + 100
    lines = wrap_text(draw, short_text(text, 240), body_font, WIDTH - 210)
    for line in lines[:4]:
        draw.text((100, y), line, font=body_font, fill=(255, 255, 255, 255))
        y += 58

    img.save(path, "PNG")
    return path


def render_scene(scene, scene_index, gameplay_path, source_images, audio_path, output_path, job):
    audio_duration = ffprobe_duration(audio_path)
    scene_duration = max(float(scene["duration"]), audio_duration + 0.5, 2.5)

    seek = random_seek(gameplay_path, scene_duration, seed=scene_index * 999 + len(clean_text(job.get("topic"))))
    source_image = source_images[(scene_index - 1) % len(source_images)]

    subtitle_png = TEMP_DIR / f"subtitle_{scene_index:02d}.png"
    make_subtitle_overlay(subtitle_png, scene.get("title", f"Scene {scene_index}"), scene.get("voiceOver", ""))

    video_no_audio = TEMP_DIR / f"scene_{scene_index:02d}_video.mp4"

    filter_complex = (
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},eq=brightness=-0.12:saturation=1.08,"
        f"fps={FPS},setsar=1[bg];"
        f"[1:v]scale=920:980:force_original_aspect_ratio=decrease,format=rgba[src];"
        f"[bg][src]overlay=x=(W-w)/2:y=250:format=auto[tmp1];"
        f"[tmp1][2:v]overlay=x=0:y=0:format=auto[v]"
    )

    run(
        [
            "ffmpeg", "-y",
            "-ss", str(seek),
            "-stream_loop", "-1",
            "-t", str(scene_duration),
            "-i", str(gameplay_path),
            "-loop", "1",
            "-t", str(scene_duration),
            "-i", str(source_image),
            "-loop", "1",
            "-t", str(scene_duration),
            "-i", str(subtitle_png),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-t", str(scene_duration),
            "-r", str(FPS),
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(video_no_audio),
        ],
        f"Render scene {scene_index} visual",
    )

    run(
        [
            "ffmpeg", "-y",
            "-i", str(video_no_audio),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "160k",
            "-shortest",
            str(output_path),
        ],
        f"Merge scene {scene_index} voice",
    )

    return output_path


def concat_scenes(scene_files, output_path):
    concat_file = TEMP_DIR / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for item in scene_files:
            f.write("file '" + str(item.resolve()).replace("'", "'\\''") + "'\n")

    run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ],
        "Concat final video",
    )


def main():
    ensure_dirs()

    if len(sys.argv) < 3:
        raise SystemExit("Usage: python3 render_full_selected_rank.py input/job_payload.json output/final_video.mp4")

    job_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    job = json.loads(job_path.read_text(encoding="utf-8"))

    print("FULL SELECTED RANK RENDER")
    print("Job ID:", job.get("jobId"))
    print("Topic:", job.get("topic"))
    print("Selected rank:", job.get("selectedRank"))
        voice_settings = get_voice_settings(
        job.get("voiceLang") or job.get("language") or "English",
        job.get("voiceIntonation") or "Calm Explainer",
    )

    print("Output language:", voice_settings["language"])
    print("TTS voice:", voice_settings["voice"])
    print("Voice intonation:", voice_settings["intonation"])

    gameplay_urls = job.get("gameplayUrls") or []
    if not gameplay_urls:
        raise RuntimeError("No gameplayUrls in payload")

    gameplays = []
    for idx, url in enumerate(gameplay_urls[:5], start=1):
        gameplays.append(download_gameplay(url, idx))

    scenes = normalize_scenes(job)
    scene_images = prepare_scene_images(job, scenes)

    scene_outputs = []
    for index, scene in enumerate(scenes, start=1):
        audio_path = AUDIO_DIR / f"scene_{index:02d}.mp3"
               original_voice_text = scene["voiceOver"]
        voice_text = translate_for_language(original_voice_text, voice_settings["target_code"])
        scene["voiceOver"] = voice_text

        print("Scene", index, "|", scene["title"])
        print("VO original:", original_voice_text)
        print("VO final:", voice_text)

        asyncio.run(
            generate_tts(
                voice_text,
                audio_path,
                voice=voice_settings["voice"],
                rate=voice_settings["rate"],
                pitch=voice_settings["pitch"],
            )
        )

        gameplay = pick_gameplay(gameplays, index - 1)
        out = TEMP_DIR / f"scene_{index:02d}_with_voice.mp4"

        render_scene(scene, index, gameplay, scene_images[index - 1], audio_path, out, job)
        scene_outputs.append(out)

    concat_scenes(scene_outputs, output_path)

    if not output_path.exists() or output_path.stat().st_size < 100_000:
        raise RuntimeError("Final output invalid")

    print("DONE:", output_path)
    print("Size:", output_path.stat().st_size)


if __name__ == "__main__":
    main()
