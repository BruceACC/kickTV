"""
KickTV — Stream Engine

Manages the FFmpeg process for continuous 24/7 streaming to Kick.
Features:
  - Gapless Master-Worker architecture (never drops connection)
  - Automatic FFmpeg command construction
  - Real-time stderr parsing for metrics (FPS, bitrate, dropped frames)
  - Automatic reconnection with exponential backoff
  - Graceful transitions between videos
"""

from __future__ import annotations

import asyncio
import logging
import re
import signal
import time
import shutil
from datetime import datetime
from typing import Optional

from app.config import settings
from app.core.queue_manager import SmartQueue, queue
from app.database import db
from app.models import StreamState, StreamStatus, VideoResult

logger = logging.getLogger("kicktv")
ffmpeg_logger = logging.getLogger("kicktv.ffmpeg")

# Regex patterns for parsing FFmpeg output
RE_FPS = re.compile(r"fps=\s*([\d.]+)")
RE_BITRATE = re.compile(r"bitrate=\s*([\d.]+kbits/s)")
RE_SIZE = re.compile(r"size=\s*(\S+)")
RE_TIME = re.compile(r"time=\s*(\d{2}:\d{2}:\d{2}\.\d+)")
RE_FRAME = re.compile(r"frame=\s*(\d+)")
RE_DROP = re.compile(r"drop=\s*(\d+)")


class StreamEngine:
    """
    FFmpeg-based stream engine that plays videos from the queue
    and transmits them continuously to a Kick RTMPS endpoint.
    """

    def __init__(self, video_queue: Optional[SmartQueue] = None) -> None:
        self._queue = video_queue or queue
        self._process: Optional[asyncio.subprocess.Process] = None
        self._master_process: Optional[asyncio.subprocess.Process] = None
        self._status = StreamStatus()
        self._running = False
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 10

    @property
    def status(self) -> StreamStatus:
        """Get the current stream status."""
        if self._status.started_at:
            self._status.uptime_seconds = int(
                (datetime.utcnow() - self._status.started_at).total_seconds()
            )
        return self._status

    @property
    def is_running(self) -> bool:
        return self._running

    async def _start_master_process(self) -> bool:
        """Start the master FFmpeg process that connects to Kick."""
        if self._master_process and self._master_process.returncode is None:
            return True

        output_format = "mpegts" if settings.stream_full_url.startswith("srt://") else "flv"

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-stats",
            "-f", "mpegts",
            "-fflags", "+genpts",
            "-i", "pipe:0",
            "-c", "copy"
        ]

        if settings.local_preview:
            # Clear old HLS segments
            if settings.abs_hls_dir.exists():
                shutil.rmtree(settings.abs_hls_dir, ignore_errors=True)
            settings.abs_hls_dir.mkdir(parents=True, exist_ok=True)
            
            hls_path = str(settings.abs_hls_dir / "stream.m3u8").replace("\\", "/")
            tee_mapping = f"[f={output_format}]{settings.stream_full_url}|[f=hls:hls_time=4:hls_list_size=3:hls_flags=delete_segments]{hls_path}"
            cmd.extend(["-map", "0", "-f", "tee", tee_mapping])
        else:
            cmd.extend(["-f", output_format, settings.stream_full_url])

        ffmpeg_logger.info("Starting Master FFmpeg: %s", " ".join(cmd))
        try:
            self._master_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            # Read output in background for metrics
            asyncio.create_task(self._read_ffmpeg_output(self._master_process))
            return True
        except Exception as e:
            logger.error("Failed to start Master FFmpeg: %s", e)
            return False

    async def _kill_master_process(self) -> None:
        """Terminate the master FFmpeg process."""
        if self._master_process and self._master_process.returncode is None:
            try:
                self._master_process.terminate()
                try:
                    await asyncio.wait_for(self._master_process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._master_process.kill()
                    await self._master_process.wait()
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error("Error killing Master FFmpeg: %s", e)
        self._master_process = None

    def _build_ffmpeg_command_v2(self, input_source: str) -> list[str]:
        """
        Simplified, robust FFmpeg command that handles both local files
        and remote URLs, with silent audio fallback. Outputs MPEG-TS.
        """
        w, h = settings.resolution_width, settings.resolution_height

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error", # Only log errors for workers
            "-y",
        ]

        if input_source.startswith(("http://", "https://")):
            cmd.extend([
                "-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36\r\nReferer: https://unlimplay.com/\r\n",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "10",
                "-reconnect_on_network_error", "1",
                "-reconnect_on_http_error", "4xx,5xx",
            ])

        cmd.extend([
            # Read at native speed
            "-re",
            # Input video
            "-i", input_source,
            # Video encoding
            "-c:v", "libx264",
            "-preset", settings.preset,
            "-tune", "film",
            "-b:v", settings.bitrate,
            "-maxrate", settings.bitrate,
            "-bufsize", str(int(settings.bitrate.replace("k", "")) * 3) + "k",
            "-pix_fmt", "yuv420p",
            "-g", str(settings.fps * 2),
            "-r", str(settings.fps),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
            # Audio encoding
            "-c:a", "aac",
            "-b:a", settings.audio_bitrate,
            "-ac", "2",
            "-ar", "44100",
            # Output format for pipe
            "-f", "mpegts",
            "-muxdelay", "0",
            "-muxpreload", "0",
            "pipe:1"
        ])

        return cmd

    async def _read_ffmpeg_output(self, process: asyncio.subprocess.Process) -> None:
        """Read and parse FFmpeg's stderr output for metrics."""
        if not process.stderr:
            return

        while True:
            try:
                line = await asyncio.wait_for(
                    process.stderr.readline(), timeout=30
                )
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

            if not line:
                break

            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            ffmpeg_logger.debug(text)

            # Parse metrics from progress lines
            fps_match = RE_FPS.search(text)
            if fps_match:
                self._status.current_fps = float(fps_match.group(1))

            bitrate_match = RE_BITRATE.search(text)
            if bitrate_match:
                self._status.current_bitrate = bitrate_match.group(1)

            drop_match = RE_DROP.search(text)
            if drop_match:
                self._status.frames_dropped = int(drop_match.group(1))

            # Log warnings and errors
            if any(kw in text.lower() for kw in ("error", "fail", "warning", "broken")):
                ffmpeg_logger.warning("FFmpeg: %s", text)

    async def _play_video(self, video: VideoResult) -> bool:
        """
        Stream a single video using Worker FFmpeg piped to Master FFmpeg.
        Returns True if playback completed normally, False on error.
        """
        logger.info(
            ">> Playing: '%s' [%s] by %s from %s",
            video.title[:50],
            video.category.value,
            video.author[:30],
            video.provider.value,
        )

        self._status.current_video = video
        self._status.next_video = self._queue.peek()

        # Ensure Master is running
        if not await self._start_master_process():
            return False

        cmd = self._build_ffmpeg_command_v2(video.url)
        ffmpeg_logger.info("Worker CMD: %s", " ".join(cmd[:5]) + " ...")

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self._status.ffmpeg_pid = self._process.pid if self._process else None
            
            # Helper to pipe data from worker stdout to master stdin
            async def _pipe_data():
                try:
                    while self._process and self._process.stdout and not self._process.stdout.at_eof():
                        chunk = await self._process.stdout.read(65536)
                        if not chunk: break
                        if self._master_process and self._master_process.stdin:
                            self._master_process.stdin.write(chunk)
                            await self._master_process.stdin.drain()
                except Exception as e:
                    logger.error("Pipe error during streaming: %s", e)
                    if self._process:
                        try:
                            self._process.kill()
                        except Exception:
                            pass

            # Helper to discard worker stderr (or log it)
            async def _discard_stderr():
                if self._process and self._process.stderr:
                    while not self._process.stderr.at_eof():
                        try:
                            line = await self._process.stderr.readline()
                            if not line: break
                            # text = line.decode('utf-8', errors='ignore').strip()
                            # if text: ffmpeg_logger.debug("Worker: " + text)
                        except Exception: break

            pipe_task = asyncio.create_task(_pipe_data())
            stderr_task = asyncio.create_task(_discard_stderr())

            # Wait for process to complete or stop signal
            while not self._stop_event.is_set():
                try:
                    return_code = await asyncio.wait_for(
                        self._process.wait(), timeout=2.0
                    )
                    # Process finished
                    pipe_task.cancel()
                    stderr_task.cancel()

                    if return_code == 0:
                        logger.info("[OK] Completed: '%s'", video.title[:50])
                        self._consecutive_errors = 0
                        self._reconnect_delay = 1.0
                        return True
                    else:
                        logger.warning(
                            "[FAIL] FFmpeg exited with code %d for '%s'",
                            return_code, video.title[:50],
                        )
                        return False
                except asyncio.TimeoutError:
                    continue  # Still running, check stop event

            # Stop was requested
            pipe_task.cancel()
            stderr_task.cancel()
            return False

        except FileNotFoundError:
            logger.error("FFmpeg not found. Please install FFmpeg.")
            await db.log_error(
                message="FFmpeg not found",
                source="stream_engine",
                error_type="ffmpeg_missing",
            )
            return False
        except Exception as e:
            logger.error("FFmpeg error: %s", e)
            await db.log_error(
                message=str(e),
                source="stream_engine",
                error_type="ffmpeg_error",
                video_url=video.url,
            )
            return False
        finally:
            await self._kill_ffmpeg()

    async def _kill_ffmpeg(self) -> None:
        """Terminate the worker FFmpeg process if running."""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error("Error killing Worker FFmpeg: %s", e)
        self._process = None
        self._status.ffmpeg_pid = None

    async def _stream_loop(self) -> None:
        """
        Main streaming loop. Plays videos from the queue continuously.
        Handles errors with exponential backoff.
        """
        logger.info("[STREAM] Stream loop started")
        self._status.state = StreamState.LIVE
        self._status.started_at = datetime.utcnow()

        while self._running and not self._stop_event.is_set():
            # Get next video
            video = await self._queue.next()

            if not video:
                logger.warning("Queue empty. Waiting for content...")
                self._status.state = StreamState.RECONNECTING
                await asyncio.sleep(5)
                # Try to fill the queue
                await self._queue.fill()
                continue

            # Play the video
            success = await self._play_video(video)

            if self._stop_event.is_set():
                break

            if not success:
                self._consecutive_errors += 1
                self._status.reconnect_count += 1

                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.error(
                        "Too many consecutive errors (%d). Pausing stream.",
                        self._consecutive_errors,
                    )
                    self._status.state = StreamState.ERROR
                    await db.log_error(
                        message=f"Too many consecutive errors: {self._consecutive_errors}",
                        source="stream_engine",
                        error_type="max_errors_reached",
                    )
                    await asyncio.sleep(30)
                    self._consecutive_errors = 0
                    continue

                # Exponential backoff
                self._status.state = StreamState.RECONNECTING
                logger.info(
                    "Reconnecting in %.1fs... (attempt %d)",
                    self._reconnect_delay,
                    self._consecutive_errors,
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )
                # Master might be dead or the connection dropped, force restart
                await self._kill_master_process()
            else:
                self._status.total_videos_played += 1
                self._status.state = StreamState.LIVE

        logger.info("[STREAM] Stream loop ended")
        self._status.state = StreamState.STOPPED

    async def start(self) -> bool:
        """Start the streaming engine."""
        if self._running:
            logger.warning("Stream is already running")
            return False

        logger.info("Starting stream engine...")
        self._running = True
        self._stop_event.clear()
        self._status = StreamStatus(state=StreamState.STARTING)
        self._consecutive_errors = 0
        self._reconnect_delay = 1.0

        # Ensure queue has content
        await self._queue.fill()

        # Start the stream loop as a background task
        self._task = asyncio.create_task(self._stream_loop())
        logger.info("[OK] Stream engine started")
        return True

    async def stop(self) -> bool:
        """Stop the streaming engine."""
        if not self._running:
            logger.warning("Stream is not running")
            return False

        logger.info("Stopping stream engine...")
        self._running = False
        self._stop_event.set()

        # Kill FFmpeg worker and master
        await self._kill_ffmpeg()
        await self._kill_master_process()

        # Wait for task to finish
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()

        self._status.state = StreamState.STOPPED
        self._status.current_video = None
        self._status.current_fps = 0
        self._status.current_bitrate = "0k"
        logger.info("[OK] Stream engine stopped")
        return True

    async def restart(self) -> bool:
        """Restart the streaming engine."""
        logger.info("Restarting stream engine...")
        await self.stop()
        await asyncio.sleep(2)
        return await self.start()

    async def skip_current(self) -> bool:
        """Skip the currently playing video."""
        if not self._running:
            return False
        logger.info("Skipping current video...")
        await self._kill_ffmpeg()
        return True


# Singleton
engine = StreamEngine()
