# VoiceRAG demo video script

**Target length:** about 90 seconds  
**Demo setup:** Start the Docker Compose stack, sign in, and prepare either a short local video or a YouTube URL that `yt-dlp` can access. For a generated answer, configure an LLM provider that is enabled for your account. If it is not enabled, show VoiceRAG's cited transcript-excerpt fallback.

| Time | Screen action | Narration |
| --- | --- | --- |
| 0:00–0:08 | Show the VoiceRAG home screen and the Video Intelligence panel. | “This is VoiceRAG, a tool for turning long recordings into searchable, question-ready transcripts.” |
| 0:08–0:20 | Choose a local video or paste a supported YouTube link, then start import. | “I can upload a video or bring in a YouTube link. VoiceRAG extracts the audio and sends it to AssemblyAI for transcription.” |
| 0:20–0:34 | Open the completed document and scroll through its transcript and timestamps. | “Once processing finishes, I can review the recognized speech and jump to the source time that matters.” |
| 0:34–0:51 | Open key points, then enter a question tied to the recording. | “I can skim the key points, then ask a specific question about what was said instead of searching the whole video manually.” |
| 0:51–1:08 | Show the answer and its transcript citations. Open one cited passage or timestamp. | “VoiceRAG retrieves relevant transcript passages and returns source citations, so I can check the answer against the recording.” |
| 1:08–1:20 | Ask a question unrelated to the video, or show the unavailable-model fallback if Gateway access is not configured. | “If the transcript does not support an answer, the app can say so. If the selected answer model is unavailable, it clearly shows transcript excerpts instead of presenting them as generated output.” |
| 1:20–1:30 | Return to the project title or show the repository link. | “VoiceRAG makes spoken content easier to review, search, and use. The source and setup instructions are available on GitHub.” |

## Recording notes

- Use a short video with clear speech so import and transcription are easy to follow.
- Hide account credentials and API keys from the recording.
- Wait for transcription and indexing to finish before recording the question-and-answer portion.
- YouTube import needs outbound network access and a video that `yt-dlp` can access.
- The AssemblyAI LLM Gateway model tested for this project was not enabled on the configured account. For a fully generated answer demo, enable a Gateway model or configure an OpenAI-compatible provider first. Otherwise, present the transcript-excerpt fallback accurately.
