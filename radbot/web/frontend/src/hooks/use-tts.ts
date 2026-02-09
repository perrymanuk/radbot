import { useRef, useState, useCallback } from "react";
import * as api from "@/lib/api";

export function useTTS() {
  const [playing, setPlaying] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const queueRef = useRef<string[]>([]);
  const playingRef = useRef(false);

  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext();
    }
    return audioCtxRef.current;
  }, []);

  const playNext = useCallback(async () => {
    if (playingRef.current || queueRef.current.length === 0) return;

    playingRef.current = true;
    setPlaying(true);

    const text = queueRef.current.shift()!;

    try {
      const audioData = await api.synthesizeSpeech(text);
      const ctx = getAudioContext();
      const buffer = await ctx.decodeAudioData(audioData);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);

      source.onended = () => {
        playingRef.current = false;
        if (queueRef.current.length > 0) {
          playNext();
        } else {
          setPlaying(false);
        }
      };

      source.start();
    } catch (err) {
      console.error("[TTS] Playback error:", err);
      playingRef.current = false;
      setPlaying(false);
      // Try next in queue
      if (queueRef.current.length > 0) {
        playNext();
      }
    }
  }, [getAudioContext]);

  const speak = useCallback(
    (text: string) => {
      queueRef.current.push(text);
      if (!playingRef.current) {
        playNext();
      }
    },
    [playNext],
  );

  const stop = useCallback(() => {
    queueRef.current = [];
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    playingRef.current = false;
    setPlaying(false);
  }, []);

  return { speak, stop, playing };
}
