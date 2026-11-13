"""Add offline macOS narration and readable captions to the verified browser recording."""

import json
import os
import subprocess
import textwrap
import wave
from pathlib import Path

OUT = Path("output/video")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
STORY = {
    "welcome": ("LeanCode / Arpit's workspace", "Meet LeanCode: a coding agent built around focused context, human approval, and spending controls. This is the actual app, using a disposable Python repository."),
    "repositories": ("01 / Choose the right boundary", "Repository policy controls where code can go. Public projects can use cloud models. Confidential projects require an allowed local model, with external documentation search disabled."),
    "task": ("02 / Give the agent a focused task", "Here, zero is incorrectly treated as positive. We ask LeanCode to inspect the code and tests, consult the approved Python documentation topic, and propose the smallest fix. Gemini runs through Bifrost; Tavily retrieves public documentation."),
    "patch": ("03 / Review before anything changes", "LeanCode pauses at the exact diff. The proposed change replaces greater than or equal with strictly greater than. The original file remains untouched until this approval."),
    "command": ("04 / Approve the exact test command", "Applying the patch does not grant permission to run commands. The agent asks separately for this unit test command. Approved tests run inside the restricted Docker sandbox."),
    "result": ("05 / Verify the result", "The tests pass on the patched snapshot, and the real agent completes the task. The workbench reports measured tokens and cost. These are actual results from this run, not simulated model responses."),
    "privacy": ("06 / Confidential means local only", "Now we select a confidential repository. No permitted local model is configured, so LeanCode blocks the task before any model call. This demonstrates the privacy boundary, not offline task completion."),
    "budget": ("07 / Enforce the spending limit", "A separate demo account has zero available budget. LeanCode blocks this request before dispatch. The recording checks that both blocked examples made zero model calls."),
    "benchmarks": ("LeanCode / Focus. Review. Verify.", "LeanCode makes coding work reviewable and spending visible. Comparative token savings and cross provider failover still need validation. The walkthrough is edited for pace; the original recording and run evidence are preserved."),
}


def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def main():
    chapters = json.loads((OUT / "chapters.json").read_text())
    evidence = json.loads((OUT / "evidence.json").read_text())
    assert evidence["completed"]["status"] == "completed"
    assert evidence["budget"]["status"] == "blocked"
    assert any("Budget exhausted" in e["data"].get("message", "") for e in evidence["budget"]["events"])
    for guard in ("privacy", "budget"):
        assert evidence[guard]["state"].get("model_calls", 0) == 0
    assert any(e["data"].get("message", "").startswith("Docs:") for e in evidence["completed"]["events"]), "Narration requires actual documentation retrieval"
    clips, subtitles, elapsed = [], [], 0.0
    for index, (chapter, following) in enumerate(zip(chapters, chapters[1:])):
        title, narration = STORY[chapter["id"]]
        if chapter["id"] == "task" and evidence.get("recoveredProviderError"):
            narration += " A temporary provider error is resumed from saved progress on the same provider."
        prefix = OUT / f"chapter-{index:02}"
        prefix.with_suffix(".txt").write_text(narration)
        run(["say", "-v", "Samantha", "-r", "163", "--data-format=BEI16@22050", "-f", str(prefix.with_suffix(".txt")), "-o", str(prefix.with_suffix(".aiff"))])
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(prefix.with_suffix(".aiff")), str(prefix.with_suffix(".wav"))])
        with wave.open(str(prefix.with_suffix(".wav"))) as sound:
            duration = sound.getnframes() / sound.getframerate() + 1
        source_duration = chapter.get("end", following["start"]) - chapter["start"]
        assert source_duration > 0 and duration > 0
        prefix.with_suffix(".title").write_text(title)
        prefix.with_suffix(".caption").write_text(textwrap.fill(narration, width=145))
        filters = (
            f"[0:v]setpts={duration / source_duration}*(PTS-STARTPTS),fps=30,scale=1600:900,"
            "pad=1920:1080:160:80:color=0xf7f7f4,"
            f"drawtext=fontfile='{FONT}':textfile='{prefix.with_suffix('.title')}':fontcolor=0x234638:fontsize=25:x=160:y=30,"
            f"drawtext=fontfile='{FONT}':textfile='{prefix.with_suffix('.caption')}':fontcolor=0x242b27:fontsize=21:line_spacing=5:x=160:y=995,"
            "drawtext=fontfile='" + FONT + "':text='EDITED WALKTHROUGH':fontcolor=0x717a74:fontsize=17:x=1530:y=35,format=yuv420p[v];"
            "[1:a]apad[a]"
        )
        clip = prefix.with_suffix(".mp4")
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(chapter["start"]), "-t", str(source_duration), "-i", str(OUT / chapter.get("file", "leancode-demo-raw.webm")), "-i", str(prefix.with_suffix(".aiff")), "-filter_complex", filters, "-map", "[v]", "-map", "[a]", "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(clip)])
        clips.append(f"file '{clip.name}'")
        subtitles.append(f"{index + 1}\n{timestamp(elapsed)} --> {timestamp(elapsed + duration)}\n{narration}\n")
        elapsed += duration
        print(f"Rendered {chapter['id']} ({duration:.1f}s)", flush=True)
    (OUT / "concat.txt").write_text("\n".join(clips))
    (OUT / "leancode-demo.srt").write_text("\n".join(subtitles))
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(OUT / "concat.txt"), "-c", "copy", "-movflags", "+faststart", str(OUT / "leancode-demo.mp4")])
    print(f"Finished {elapsed:.1f}s narrated demo")


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    return f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:{milliseconds // 1000 % 60:02},{milliseconds % 1000:03}"


if __name__ == "__main__":
    main()
