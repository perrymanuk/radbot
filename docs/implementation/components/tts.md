# Text-to-Speech (TTS)

The TTS system adds audio playback of agent responses in the web UI using Google Cloud Text-to-Speech.

## Architecture

- **Backend**: Google Cloud TTS API via `google-cloud-texttospeech`
- **Service**: `TTSService` singleton with in-memory LRU cache
- **API**: `POST /api/tts/synthesize` returns MP3 audio
- **Frontend**: `TTSManager` class handles playback, queue, and auto-play

## Web UI Features

### Play Button
Every assistant message has a small play button (triangle icon) in the top-right corner. Click it to hear the message read aloud. Click again (square icon) to stop.

The button is subtly visible (30% opacity) and becomes more prominent on hover.

### Auto-Play Toggle
The "TTS" button in the header bar toggles auto-play mode:
- **OFF** (default): Messages are only read when you click the play button
- **ON** (green border): New assistant messages are automatically read aloud

The auto-play preference is saved in localStorage and persists across sessions.

### How Audio Playback Works
1. Click play button (or auto-play triggers)
2. Frontend sends message text to `/api/tts/synthesize`
3. Backend strips markdown, code blocks, and HTML from the text
4. Google Cloud TTS synthesizes MP3 audio
5. Audio is cached server-side (LRU, max 100 entries)
6. MP3 is streamed to browser and played via HTML5 `Audio()`

## Prerequisites

Google Cloud TTS requires authentication. Set up one of:

1. **Application Default Credentials** (recommended):
   ```bash
   gcloud auth application-default login
   ```

2. **Service Account**:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
   ```

3. The Google Cloud project must have the Text-to-Speech API enabled.

## Configuration

In `config.yaml`:
```yaml
tts:
  enabled: true
  voice_name: "en-US-Studio-O"
  language_code: "en-US"
  speaking_rate: 1.0
  pitch: 0.0
  max_text_length: 5000
  auto_play: false
```

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `true` | Enable/disable TTS |
| `voice_name` | `en-US-Studio-O` | Google Cloud TTS voice |
| `language_code` | `en-US` | Language code |
| `speaking_rate` | `1.0` | Speed (0.25 to 4.0) |
| `pitch` | `0.0` | Pitch in semitones (-20 to 20) |
| `max_text_length` | `5000` | Max characters to synthesize |
| `auto_play` | `false` | Default auto-play state |

### Available Voices

Browse voices at: https://cloud.google.com/text-to-speech/docs/voices

Popular options:
- `en-US-Studio-O` - Natural male voice
- `en-US-Studio-Q` - Natural female voice
- `en-US-Neural2-D` - Neural male voice
- `en-US-Neural2-F` - Neural female voice

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/tts/synthesize` | Synthesize text to MP3 audio |

Request body:
```json
{
  "text": "Hello, this is a test."
}
```

Response: MP3 audio bytes (`audio/mpeg` content type).

## Text Cleaning

Before synthesis, the service strips:
- Markdown formatting (`**bold**`, `*italic*`, `# headers`, etc.)
- Code blocks (``` fenced and inline)
- HTML tags
- URLs
- Excessive whitespace

## Files

| File | Purpose |
|------|---------|
| `radbot/tools/tts/__init__.py` | Package exports |
| `radbot/tools/tts/tts_service.py` | TTS service singleton + text cleaning |
| `radbot/web/api/tts.py` | REST API router |
| `radbot/web/static/js/tts.js` | Frontend TTSManager + play button |
| `radbot/web/static/css/messages.css` | Play button + auto-play toggle styling |
