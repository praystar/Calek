"""Transcription route — audio → text using OpenAI Whisper."""

from fastapi import APIRouter, UploadFile, File, HTTPException
import tempfile, shutil, os, logging

router = APIRouter()
logger = logging.getLogger(__name__)

_whisper_model = None

def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        # "base" is fast, use "small" or "medium" for better accuracy
        _whisper_model = whisper.load_model("base")
        logger.info("Whisper model loaded")
    return _whisper_model


@router.post("")
async def transcribe_audio(audio: UploadFile = File(...)):
    """
    Transcribe uploaded audio to text using Whisper.

    Accepts: webm, mp3, wav, m4a, ogg
    """
    allowed_types = {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4",
                     "audio/ogg", "audio/x-wav", "audio/wave"}
    if audio.content_type not in allowed_types:
        # Be lenient — browser MediaRecorder may set odd mime types
        logger.warning(f"Unexpected content type: {audio.content_type}")

    tmpdir = tempfile.mkdtemp()
    try:
        ext = ".webm" if "webm" in (audio.content_type or "") else ".wav"
        audio_path = os.path.join(tmpdir, f"recording{ext}")

        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        file_size = os.path.getsize(audio_path)
        if file_size < 1000:
            raise HTTPException(400, "Audio file too small — nothing recorded?")

        model = get_whisper()
        result = model.transcribe(audio_path, language="en", task="transcribe")
        transcript = result["text"].strip()

        if not transcript:
            raise HTTPException(422, "Could not transcribe — speech unclear or too short")

        return {
            "transcript": transcript,
            "language": result.get("language", "en"),
            "duration_s": result.get("duration"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(500, f"Transcription failed: {str(e)}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
