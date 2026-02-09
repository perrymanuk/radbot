import { useRef, useState, useCallback } from "react";
import * as api from "@/lib/api";

type STTState = "idle" | "recording" | "processing";

export function useSTT(onTranscript: (text: string) => void) {
  const [state, setState] = useState<STTState>("idle");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach((t) => t.stop());

        if (chunksRef.current.length === 0) {
          setState("idle");
          return;
        }

        setState("processing");

        try {
          const blob = new Blob(chunksRef.current, { type: mimeType });
          const result = await api.transcribeAudio(blob);
          if (result.text) {
            onTranscript(result.text);
          }
        } catch (err) {
          console.error("[STT] Transcription error:", err);
        }

        setState("idle");
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setState("recording");
    } catch (err) {
      console.error("[STT] Failed to access microphone:", err);
      setState("idle");
    }
  }, [onTranscript]);

  const stop = useCallback(() => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const toggle = useCallback(() => {
    if (state === "recording") {
      stop();
    } else if (state === "idle") {
      start();
    }
    // Don't toggle during processing
  }, [state, start, stop]);

  return { state, start, stop, toggle };
}
