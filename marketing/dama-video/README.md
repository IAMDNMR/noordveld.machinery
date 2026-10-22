# DAMA Drinks Amsterdam: promo video (9:16, 33 s)

A Remotion motion-graphics composition. Every scene is a function of time; timings, captions, VO placement and SFX cues come from `src/timeline.json`.

- 0–8 s `Opening`: kinetic type: NV-4500 telemetry flatlines, "A machine is down.", the discontinued AS-411-C tilt cylinder (cut out by `scripts/cutout.py`), three catalogues with no match.
- 8–14 s `Yoa`: real footage of the Noordveld Parts Intelligence app ("Find AS-411-C" → NVM-1040-HY) inside a phone.
- 14–17 s `Turn`, 17–27 s `Gecko` (BlueGecko + Falcon/Cheetah/Owl), 27–33 s `Invite` (The Sheryl at sunset + event card).

```bash
npm install
python -I scripts/vo.py                 # voiceover lines -> audio/*.mp3 (Edge neural TTS, en-GB-RyanNeural)
python -I scripts/audio_mix.py          # synthesised music + SFX + VO with ducking -> audio/mix.wav
python -I scripts/record_platform.py    # needs the site on :5180 + API; records assets/platform/*.jpg
npm run studio                          # preview in Remotion Studio
npx remotion render src/index.ts DamaPromo out/video.mp4 --public-dir=assets --crf=18 --muted
ffmpeg -i out/video.mp4 -i audio/mix.wav -map 0:v -map 1:a -c:v libx264 -crf 19 -pix_fmt yuv420p -movflags +faststart -af loudnorm=I=-14:TP=-1:LRA=11 -c:a aac -b:a 192k -shortest out/DAMA-Drinks-Amsterdam_9x16.mp4
```

`scripts/prepare.py` rebuilds logos and part photos in `assets/`; `scripts/grade_sheryl.py <folder>` grades The Sheryl photos (b-events.amsterdam) to sunset.
To swap in a recorded voiceover, replace the files in `audio/` and adjust the `vo` start times in `src/timeline.json`.
