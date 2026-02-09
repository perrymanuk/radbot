import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  FormInput,
  FormToggle,
  FormDropdown,
  FormSlider,
  ActionBar,
} from "@/components/admin/FormFields";

const VOICE_NAMES = [
  "en-US-Casual-K",
  "en-US-Journey-D",
  "en-US-Journey-F",
  "en-US-Neural2-A",
  "en-US-Neural2-C",
  "en-US-Neural2-D",
  "en-US-Neural2-F",
  "en-US-Standard-A",
  "en-US-Standard-B",
  "en-US-Wavenet-A",
  "en-US-Wavenet-D",
];

// ── TTS Panel ─────────────────────────────────────────────
export function TTSPanel() {
  const { loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [voiceName, setVoiceName] = useState("");
  const [languageCode, setLanguageCode] = useState("en-US");
  const [speakingRate, setSpeakingRate] = useState(1.0);
  const [pitch, setPitch] = useState(0);
  const [autoPlay, setAutoPlay] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const tts = cfg?.tts ?? {};
      setEnabled(tts.enabled ?? false);
      setVoiceName(tts.voice_name ?? "");
      setLanguageCode(tts.language_code ?? "en-US");
      setSpeakingRate(tts.speaking_rate ?? 1.0);
      setPitch(tts.pitch ?? 0);
      setAutoPlay(tts.auto_play ?? false);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mergeConfigSection("tts", {
        enabled,
        voice_name: voiceName,
        language_code: languageCode,
        speaking_rate: speakingRate,
        pitch,
        auto_play: autoPlay,
      });
      toast("TTS settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <h2 className="text-lg font-semibold mb-6">Text-to-Speech</h2>

      <Card title="TTS Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Voice Name"
          value={voiceName}
          onChange={setVoiceName}
          datalist={VOICE_NAMES}
        />
        <FormInput
          label="Language Code"
          value={languageCode}
          onChange={setLanguageCode}
          placeholder="en-US"
        />
        <FormSlider
          label="Speaking Rate"
          value={speakingRate}
          onChange={setSpeakingRate}
          min={0.25}
          max={4.0}
          step={0.05}
        />
        <FormSlider
          label="Pitch"
          value={pitch}
          onChange={setPitch}
          min={-20}
          max={20}
          step={0.5}
        />
        <FormToggle label="Auto-Play" checked={autoPlay} onChange={setAutoPlay} />
        <ActionBar onSave={handleSave} saving={saving} />
      </Card>
    </div>
  );
}

// ── STT Panel ─────────────────────────────────────────────
const STT_MODELS = [
  { value: "latest_long", label: "Latest Long" },
  { value: "latest_short", label: "Latest Short" },
  { value: "command_and_search", label: "Command and Search" },
  { value: "phone_call", label: "Phone Call" },
];

export function STTPanel() {
  const { loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [languageCode, setLanguageCode] = useState("en-US");
  const [model, setModel] = useState("latest_long");
  const [autoPunctuation, setAutoPunctuation] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const stt = cfg?.stt ?? {};
      setEnabled(stt.enabled ?? false);
      setLanguageCode(stt.language_code ?? "en-US");
      setModel(stt.model ?? "latest_long");
      setAutoPunctuation(stt.auto_punctuation ?? true);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mergeConfigSection("stt", {
        enabled,
        language_code: languageCode,
        model,
        auto_punctuation: autoPunctuation,
      });
      toast("STT settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <h2 className="text-lg font-semibold mb-6">Speech-to-Text</h2>

      <Card title="STT Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Language Code"
          value={languageCode}
          onChange={setLanguageCode}
          placeholder="en-US"
        />
        <FormDropdown
          label="Model"
          value={model}
          onChange={setModel}
          options={STT_MODELS}
        />
        <FormToggle
          label="Auto Punctuation"
          checked={autoPunctuation}
          onChange={setAutoPunctuation}
        />
        <ActionBar onSave={handleSave} saving={saving} />
      </Card>
    </div>
  );
}
