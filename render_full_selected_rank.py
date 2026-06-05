import asyncio
import hashlib
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import edge_tts
import requests
from deep_translator import GoogleTranslator
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(".").resolve()
INPUT_DIR = ROOT / "input"
ASSETS_DIR = ROOT / "assets"
AUDIO_DIR = ROOT / "audio"
TEMP_DIR = ROOT / "temp"
OUTPUT_DIR = ROOT / "output"

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DEFAULT_SCENE_DURATIONS = [3, 6, 10, 11, 9, 6]
ALLOWED_TARGET_DURATIONS = [45, 60]

SCENE_DURATION_PLANS = {
    45: [3, 6, 10, 11, 9, 6],
    60: [3, 7, 15, 15, 12, 8],
}

LANGUAGE_MAP = {
    "english": {"code": "en", "male": "en-US-GuyNeural", "female": "en-US-JennyNeural"},
    "indonesian": {"code": "id", "male": "id-ID-ArdiNeural", "female": "id-ID-GadisNeural"},
    "malay": {"code": "ms", "male": "ms-MY-OsmanNeural", "female": "ms-MY-YasminNeural"},
    "turkish": {"code": "tr", "male": "tr-TR-AhmetNeural", "female": "tr-TR-EmelNeural"},
    "spanish": {"code": "es", "male": "es-ES-AlvaroNeural", "female": "es-ES-ElviraNeural"},
    "portuguese": {"code": "pt", "male": "pt-BR-AntonioNeural", "female": "pt-BR-FranciscaNeural"},
    "french": {"code": "fr", "male": "fr-FR-HenriNeural", "female": "fr-FR-DeniseNeural"},
    "german": {"code": "de", "male": "de-DE-ConradNeural", "female": "de-DE-KatjaNeural"},
    "italian": {"code": "it", "male": "it-IT-DiegoNeural", "female": "it-IT-ElsaNeural"},
    "dutch": {"code": "nl", "male": "nl-NL-MaartenNeural", "female": "nl-NL-ColetteNeural"},
    "russian": {"code": "ru", "male": "ru-RU-DmitryNeural", "female": "ru-RU-SvetlanaNeural"},
    "arabic": {"code": "ar", "male": "ar-SA-HamedNeural", "female": "ar-SA-ZariyahNeural"},
    "hindi": {"code": "hi", "male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"},
    "japanese": {"code": "ja", "male": "ja-JP-KeitaNeural", "female": "ja-JP-NanamiNeural"},
    "korean": {"code": "ko", "male": "ko-KR-InJoonNeural", "female": "ko-KR-SunHiNeural"},
    "chinese": {"code": "zh-CN", "male": "zh-CN-YunxiNeural", "female": "zh-CN-XiaoxiaoNeural"},
    "vietnamese": {"code": "vi", "male": "vi-VN-NamMinhNeural", "female": "vi-VN-HoaiMyNeural"},
    "thai": {"code": "th", "male": "th-TH-NiwatNeural", "female": "th-TH-PremwadeeNeural"},
    "filipino": {"code": "tl", "male": "fil-PH-AngeloNeural", "female": "fil-PH-BlessicaNeural"},
    "polish": {"code": "pl", "male": "pl-PL-MarekNeural", "female": "pl-PL-ZofiaNeural"},
}

INTONATION_MAP = {
    "calm explainer": {"rate": "+0%", "pitch": "+0Hz", "gender": "male"},
    "energetic shorts": {"rate": "+13%", "pitch": "+4Hz", "gender": "male"},
    "news reporter": {"rate": "+8%", "pitch": "+2Hz", "gender": "male"},
    "mystery voice": {"rate": "-6%", "pitch": "-4Hz", "gender": "male"},
    "friendly female": {"rate": "+5%", "pitch": "+3Hz", "gender": "female"},
}


def ensure_dirs():
    for folder in [INPUT_DIR, ASSETS_DIR, AUDIO_DIR, TEMP_DIR, OUTPUT_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def short_text(value, limit=900):
    return clean_text(value)[:limit].rstrip()
def word_count(text):
    return len(clean_text(text).split())


def build_continuous_voice_text(scenes, target_duration):
    target_words = 150 if int(target_duration) >= 60 else 110

    parts = []

    for scene in scenes:
        text = clean_text(scene.get("voiceOver"))
        if text:
            parts.append(text)

    voice_text = clean_text(" ".join(parts))

    if word_count(voice_text) < target_words:
        topic_sentences = [
            "This update matters because Roblox players and creators may feel the change directly inside the platform.",
            "The key point is to understand what changed, why the community is reacting, and what could happen next.",
            "Some players may see this as a useful improvement, while others may worry about how it affects creators or gameplay.",
            "That is why this topic is worth watching until the end before making a final opinion."
        ]

        for sentence in topic_sentences:
            if word_count(voice_text) >= target_words:
                break
            voice_text = clean_text(voice_text + " " + sentence)

    return short_text(voice_text, 1400)    


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
        duration = float(output.strip())
        return duration if duration > 0 else 0
    except Exception:
        return 0


def normalize_language(value):
    text = clean_text(value).lower()

    aliases = {
        "en": "english",
        "id": "indonesian",
        "indonesia": "indonesian",
        "bahasa indonesia": "indonesian",
        "ms": "malay",
        "malaysia": "malay",
        "tr": "turkish",
        "turkiye": "turkish",
        "turkish / türkiye": "turkish",
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
        "tl": "filipino",
        "fil": "filipino",
        "pl": "polish",
    }

    text = aliases.get(text, text)
    return text if text in LANGUAGE_MAP else "english"


def normalize_intonation(value):
    text = clean_text(value).lower()

    aliases = {
        "calm": "calm explainer",
        "calm explainer": "calm explainer",
        "energetic": "energetic shorts",
        "energetic shorts": "energetic shorts",
        "news": "news reporter",
        "news reporter": "news reporter",
        "roblox news": "news reporter",
        "mystery": "mystery voice",
        "mystery voice": "mystery voice",
        "female": "friendly female",
        "friendly female": "friendly female",
    }

    text = aliases.get(text, text)
    return text if text in INTONATION_MAP else "calm explainer"


def get_voice_settings(language_value, intonation_value):
    language = normalize_language(language_value)
    intonation = normalize_intonation(intonation_value)

    lang_data = LANGUAGE_MAP[language]
    tone_data = INTONATION_MAP[intonation]

    gender = "female" if tone_data["gender"] == "female" else "male"

    return {
        "language": language,
        "target_code": lang_data["code"],
        "voice": lang_data[gender],
        "rate": tone_data["rate"],
        "pitch": tone_data["pitch"],
        "intonation": intonation,
    }


def translate_for_language(text, target_code):
    text = clean_text(text)

    if not text or target_code == "en":
        return text

    try:
        translated = GoogleTranslator(source="auto", target=target_code).translate(text)
        return clean_text(translated) or text
    except Exception as error:
        print("Translation fallback:", error)
        return text


def extract_google_drive_id(url):
    url = clean_text(url)
    match = re.search(r"/file/d/([^/]+)", url) or re.search(r"[?&]id=([^&]+)", url)
    return match.group(1) if match else url


def download_gameplay(url, index):
    output = INPUT_DIR / f"gameplay_{index:02d}.mp4"
    file_id = extract_google_drive_id(url)

    run(
        ["gdown", f"https://drive.google.com/uc?id={file_id}", "-O", str(output)],
        f"Download gameplay {index}",
    )

    if not output.exists() or output.stat().st_size < 100_000:
        raise RuntimeError(f"Gameplay download invalid: {output}")

    return output


def pick_gameplay(gameplays, scene_index):
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

    url = value.strip()

    if not url.startswith("http"):
        return False

    lower = url.lower()

    return (
        any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp"])
        or "image" in lower
        or "thumbnail" in lower
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

                if isinstance(val, str) and any(k in key_l for k in ["image", "thumbnail", "poster", "url", "src"]):
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
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 Roblox Shorts Render Worker"},
            timeout=15,
        )

        if response.status_code >= 400 or len(response.content) < 2000:
            return False

        output.write_bytes(response.content)

        with Image.open(output) as image:
            image.verify()

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
    img = Image.new("RGB", (900, 900), (8, 24, 30))
    draw = ImageDraw.Draw(img)

    accent = (0, 225, 140)
    title_font = get_font(54, bold=True)
    body_font = get_font(36, bold=False)
    small_font = get_font(28, bold=True)

    draw.rounded_rectangle((28, 28, 872, 872), radius=36, outline=accent, width=6)
    draw.text((60, 64), f"SCENE {scene_index}", font=small_font, fill=accent)

    y = 130
    for line in wrap_text(draw, title, title_font, 780)[:4]:
        draw.text((60, y), line, font=title_font, fill=(245, 248, 250))
        y += 66

    y += 20
    for line in wrap_text(draw, body, body_font, 780)[:8]:
        draw.text((60, y), line, font=body_font, fill=(190, 215, 220))
        y += 48

    footer = short_text(topic, 90)
    draw.text((60, 810), footer, font=small_font, fill=accent)

    img.save(path, "PNG")
    return path


def make_subtitle_overlay(path, title, text):
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    title_font = get_font(42, bold=True)
    body_font = get_font(48, bold=True)
    panel_h = 380
    y0 = HEIGHT - panel_h - 80

    draw.rounded_rectangle((64, y0, WIDTH - 64, y0 + panel_h), radius=34, fill=(0, 0, 0, 170))
    draw.text((100, y0 + 34), short_text(title.upper(), 42), font=title_font, fill=(0, 235, 135, 255))

    y = y0 + 100
    for line in wrap_text(draw, short_text(text, 240), body_font, WIDTH - 210)[:4]:
        draw.text((100, y), line, font=body_font, fill=(255, 255, 255, 255))
        y += 58

    img.save(path, "PNG")
    return path


async def generate_tts(text, out_path, voice, rate, pitch):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))

    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError(f"TTS failed: {out_path}")


def parse_duration(value, fallback):
    if isinstance(value, (int, float)) and value > 0:
        return float(value)

    match = re.search(r"(\d+(?:\.\d+)?)", clean_text(value))
    return max(1.0, float(match.group(1))) if match else float(fallback)

def parse_target_video_duration(job):
    candidates = [
        job.get("videoDuration"),
        job.get("duration"),
        job.get("targetDuration"),
        job.get("durationLabel"),
    ]

    for value in candidates:
        text = clean_text(value)
        match = re.search(r"(\d+(?:\.\d+)?)", text)

        if match:
            raw = int(round(float(match.group(1))))

            if raw in ALLOWED_TARGET_DURATIONS:
                return raw

            nearest = min(ALLOWED_TARGET_DURATIONS, key=lambda item: abs(item - raw))
            return nearest

        if isinstance(value, (int, float)):
            raw = int(round(float(value)))

            if raw in ALLOWED_TARGET_DURATIONS:
                return raw

            nearest = min(ALLOWED_TARGET_DURATIONS, key=lambda item: abs(item - raw))
            return nearest

    return 45


def get_scene_duration_plan(target_duration):
    return SCENE_DURATION_PLANS.get(int(target_duration), SCENE_DURATION_PLANS[45])


def force_final_duration(input_path, output_path, target_duration):
    temp_locked = output_path.with_name(output_path.stem + "_duration_locked.mp4")
    target_duration = int(target_duration)

    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-filter_complex",
            f"[0:v]tpad=stop_mode=clone:stop_duration={target_duration},setpts=PTS-STARTPTS[v];[0:a]apad[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            str(target_duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(temp_locked),
        ],
        "Force exact final duration lock",
    )

    if not temp_locked.exists() or temp_locked.stat().st_size < 100_000:
        raise RuntimeError("Duration locked output invalid")

    temp_locked.replace(output_path)
    
def normalize_scenes(job, target_duration):
    raw_scenes = job.get("scenes") if isinstance(job.get("scenes"), list) else []
    subtitles = job.get("subtitles") if isinstance(job.get("subtitles"), list) else []

    if not raw_scenes:
        topic = clean_text(job.get("topic")) or "Roblox update"
        raw_scenes = [
            {"title": "STRONG HOOK", "voiceOver": f"Do not skip this Roblox update. {topic} could affect more players than it seems."},
            {"title": "SOURCE CONTEXT", "voiceOver": f"This topic is connected to {topic}, and the source needs to be checked before calling it official."},
            {"title": "MAIN FACT", "voiceOver": f"The main point is about {topic}. Here is what Roblox players should know."},
            {"title": "EXTRA FACT", "voiceOver": "This can affect updates, creators, items, and player reactions inside Roblox."},
            {"title": "TWIST", "voiceOver": "Community buzz can make a topic look huge, but source-backed context still matters."},
            {"title": "QUESTION + CTA", "voiceOver": "Do you think this Roblox update is a big deal? Comment your answer and follow for more Roblox updates."},
        ]

    scenes = []

    for index, scene in enumerate(raw_scenes[:6]):
        subtitle = subtitles[index] if index < len(subtitles) and isinstance(subtitles[index], dict) else {}

        voice = (
            clean_text(scene.get("voiceOver"))
            or clean_text(scene.get("voiceover"))
            or clean_text(scene.get("text"))
            or clean_text(scene.get("subtitle"))
            or clean_text(subtitle.get("text"))
            or clean_text(job.get("topic"))
        )

        if index == 0 and not voice.lower().startswith(("do not skip", "stop", "wait", "this")):
            voice = "Do not skip this Roblox update. " + voice

        if index == 5 and "comment" not in voice.lower():
            voice = voice + " Comment your answer, like if this helped, and follow for more Roblox updates."

        scenes.append({
            "id": scene.get("id") or scene.get("scene") or index + 1,
            "title": clean_text(scene.get("title")) or f"SCENE {index + 1}",
            "voiceOver": short_text(voice, 520),
            "duration": get_scene_duration_plan(target_duration)[index] if index < len(get_scene_duration_plan(target_duration)) else 5,
            "images": scene.get("images") or scene.get("imageUrls") or scene.get("visuals") or [],
        })

    return scenes


def prepare_scene_images(job, scenes):
    global_urls = collect_urls_deep(job, limit=80)
    prepared = []
    cursor = 0

    for index, scene in enumerate(scenes, start=1):
        scene_urls = collect_urls_deep(scene, limit=20)

        unique_scene_urls = []
        seen_urls = set()

        for url in scene_urls + global_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_scene_urls.append(url)

        scene_urls = unique_scene_urls

        while len(scene_urls) < 3 and cursor < len(global_urls):
            scene_urls.append(global_urls[cursor])
            cursor += 1

        files = []

        for url in scene_urls[:4]:
            digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
            out = ASSETS_DIR / f"scene_{index:02d}_{digest}.jpg"

            if download_image(url, out):
                files.append(out)

        if not files:
            print(f"No source image for scene {index}. Using gameplay only, without scene card.")

        prepared.append(files)

    return prepared

def render_scene(scene, scene_index, gameplay_path, source_images, output_path, job):
    scene_duration = max(min(float(scene["duration"]), 60.0), 2.5)
    seek = random_seek(gameplay_path, scene_duration, seed=scene_index * 999 + len(clean_text(job.get("topic"))))

    video_no_audio = TEMP_DIR / f"scene_{scene_index:02d}_video.mp4"

    if source_images:
        source_image = source_images[(scene_index - 1) % len(source_images)]

        filter_complex = (
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},eq=brightness=-0.12:saturation=1.08,"
            f"fps={FPS},setsar=1[bg];"
            f"[1:v]scale=920:980:force_original_aspect_ratio=decrease,format=rgba[src];"
            f"[bg][src]overlay=x=(W-w)/2:y=250:format=auto[v]"
        )

        run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(seek),
                "-stream_loop",
                "-1",
                "-t",
                str(scene_duration),
                "-i",
                str(gameplay_path),
                "-loop",
                "1",
                "-t",
                str(scene_duration),
                "-i",
                str(source_image),
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-t",
                str(scene_duration),
                "-r",
                str(FPS),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ],
            f"Render scene {scene_index} visual with source image",
        )

        return output_path

    run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(seek),
            "-stream_loop",
            "-1",
            "-t",
            str(scene_duration),
            "-i",
            str(gameplay_path),
            "-vf",
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},eq=brightness=-0.12:saturation=1.08,fps={FPS},setsar=1",
            "-t",
            str(scene_duration),
            "-r",
            str(FPS),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        f"Render scene {scene_index} gameplay only no scene card",
    )

    return output_path

def concat_scenes(scene_files, output_path):
    concat_file = TEMP_DIR / "concat.txt"

    with open(concat_file, "w", encoding="utf-8") as file:
        for item in scene_files:
            file.write("file '" + str(item.resolve()).replace("'", "'\\''") + "'\n")

    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ],
        "Concat final video",
    )
def merge_final_voice(video_path, audio_path, output_path, target_duration):
    temp_voiced = output_path.with_name(output_path.stem + "_with_continuous_voice.mp4")
    target_duration = int(target_duration)

    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            "[1:a]apad[a]",
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-t",
            str(target_duration),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(temp_voiced),
        ],
        "Merge continuous voice to final video",
    )

    if not temp_voiced.exists() or temp_voiced.stat().st_size < 100_000:
        raise RuntimeError("Continuous voice output invalid")

    temp_voiced.replace(output_path)    
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
    print("Raw voiceLang:", job.get("voiceLang"))
    print("Raw voiceIntonation:", job.get("voiceIntonation"))

    voice_settings = get_voice_settings(
        job.get("voiceLang") or job.get("language") or "English",
        job.get("voiceIntonation") or "Calm Explainer",
    )

    print("Output language:", voice_settings["language"])
    print("Target translate code:", voice_settings["target_code"])
    print("TTS voice:", voice_settings["voice"])
    print("Voice intonation:", voice_settings["intonation"])

    gameplay_urls = job.get("gameplayUrls") or []

    if not gameplay_urls:
        raise RuntimeError("No gameplayUrls in payload")

    gameplays = [
        download_gameplay(url, idx)
        for idx, url in enumerate(gameplay_urls[:5], start=1)
    ]

    target_duration = parse_target_video_duration(job)
    print("Target video duration lock:", target_duration)

    scenes = normalize_scenes(job, target_duration)
    scene_images = prepare_scene_images(job, scenes)

    scene_outputs = []

    continuous_voice_original = build_continuous_voice_text(scenes, target_duration)
    continuous_voice_text = translate_for_language(
        continuous_voice_original,
        voice_settings["target_code"]
    )

    continuous_audio_path = AUDIO_DIR / "continuous_voice.mp3"

    print("Continuous VO original:", continuous_voice_original)
    print("Continuous VO final:", continuous_voice_text)
    print("Continuous VO words:", word_count(continuous_voice_text))

    asyncio.run(
        generate_tts(
            continuous_voice_text,
            continuous_audio_path,
            voice=voice_settings["voice"],
            rate=voice_settings["rate"],
            pitch=voice_settings["pitch"],
        )
    )

    for index, scene in enumerate(scenes, start=1):
        gameplay = pick_gameplay(gameplays, index - 1)
        out = TEMP_DIR / f"scene_{index:02d}_visual_only.mp4"

        print("Scene:", index)
        print("Title:", scene["title"])
        print("Scene duration:", scene["duration"])

        render_scene(scene, index, gameplay, scene_images[index - 1], out, job)
        scene_outputs.append(out)

    concat_scenes(scene_outputs, output_path)
    merge_final_voice(output_path, continuous_audio_path, output_path, target_duration)
    force_final_duration(output_path, output_path, target_duration)

    actual_duration = ffprobe_duration(output_path)

    if actual_duration > target_duration + 0.25:
        raise RuntimeError(
            f"Final duration exceeds target. Actual={actual_duration:.2f}s Target={target_duration}s"
        )

    print("Final duration:", actual_duration)
    print("Duration target:", target_duration)

    if not output_path.exists() or output_path.stat().st_size < 100_000:
        raise RuntimeError("Final output invalid")

    print("DONE:", output_path)
    print("Size:", output_path.stat().st_size)


if __name__ == "__main__":
    main()
