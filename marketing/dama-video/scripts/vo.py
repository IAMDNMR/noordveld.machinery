"""Generate the voiceover lines with Edge neural TTS and print their durations."""
import asyncio, json, subprocess, sys
import edge_tts

VOICE = sys.argv[1] if len(sys.argv) > 1 else "en-GB-RyanNeural"
LINES = {
    "vo1": "A machine is down.",
    "vo2": "The part number's discontinued, and the answer is buried in three catalogues.",
    "vo3": "Now ask your own AI. It knows your parts, your suppliers, your history.",
    "vo4": "But AI is only as smart as the data beneath it.",
    "vo5": "Blue Gecko gets that data right, from any ERP, CRM or legacy system. On a live migration: up to seventy percent less mapping effort.",
    "vo6a": "See both, live, on the twenty-ninth of October.",
    "vo6b": "Ninth floor, B Amsterdam.",
    "vo6c": "The view and the drinks are on us.",
}

async def main():
    out = {}
    for k, text in LINES.items():
        path = f"audio/{k}.mp3"
        await edge_tts.Communicate(text, VOICE, rate=("+24%" if k in ("vo6b", "vo6c") else "+16%") if k.startswith("vo6") else "+10%").save(path)
        d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True).stdout.strip()
        out[k] = round(float(d), 2)
    print(json.dumps(out))

asyncio.run(main())
