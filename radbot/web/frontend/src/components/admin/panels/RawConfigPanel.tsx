import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import * as adminApi from "@/lib/admin-api";
import {
  FormInput,
  FormDropdown,
  FormTextarea,
  Card,
} from "@/components/admin/FormFields";

const SECTION_OPTIONS = [
  { value: "api_keys", label: "api_keys" },
  { value: "agent", label: "agent" },
  { value: "integrations", label: "integrations" },
  { value: "cache", label: "cache" },
  { value: "vector_db", label: "vector_db" },
  { value: "tts", label: "tts" },
  { value: "stt", label: "stt" },
  { value: "web", label: "web" },
  { value: "logging", label: "logging" },
  { value: "scheduler", label: "scheduler" },
  { value: "webhooks", label: "webhooks" },
  { value: "_custom", label: "(custom)" },
];

interface StoredSection {
  name: string;
  data: Record<string, any>;
  expanded: boolean;
}

export function RawConfigPanel() {
  const { liveConfig, loadLiveConfig, toast, token } = useAdminStore();

  // Editor state
  const [section, setSection] = useState("api_keys");
  const [customSection, setCustomSection] = useState("");
  const [jsonValue, setJsonValue] = useState("");
  const [saving, setSaving] = useState(false);

  // Stored sections
  const [storedSections, setStoredSections] = useState<StoredSection[]>([]);
  const [storedLoading, setStoredLoading] = useState(false);

  // Live config display
  const [liveDisplay, setLiveDisplay] = useState("");

  useEffect(() => {
    loadLiveConfig();
    loadStoredSections();
  }, []);

  useEffect(() => {
    if (liveConfig) {
      setLiveDisplay(JSON.stringify(liveConfig, null, 2));
    }
  }, [liveConfig]);

  const effectiveSection = section === "_custom" ? customSection.trim() : section;

  const loadStoredSections = async () => {
    setStoredLoading(true);
    try {
      const allConfig = await adminApi.getAllConfig(token);
      const sections: StoredSection[] = Object.entries(allConfig).map(([name, data]) => ({
        name,
        data: data as Record<string, any>,
        expanded: false,
      }));
      setStoredSections(sections);
    } catch (e: any) {
      // May not be available yet
      setStoredSections([]);
    } finally {
      setStoredLoading(false);
    }
  };

  const handleLoadCurrent = async () => {
    if (!effectiveSection) {
      toast("Enter a section name", "error");
      return;
    }
    try {
      const data = await adminApi.getConfigSection(token, effectiveSection);
      setJsonValue(JSON.stringify(data, null, 2));
      toast("Section loaded");
    } catch {
      // Fall back to live config
      try {
        const live = await adminApi.getLiveConfig(token);
        const sectionData = live[effectiveSection] || {};
        setJsonValue(JSON.stringify(sectionData, null, 2));
        toast("Loaded from live config (no stored override)");
      } catch (e: any) {
        toast("Failed to load section: " + e.message, "error");
      }
    }
  };

  const handleSaveSection = async () => {
    if (!effectiveSection) {
      toast("Enter a section name", "error");
      return;
    }

    let parsed: Record<string, any>;
    try {
      parsed = JSON.parse(jsonValue);
    } catch {
      toast("Invalid JSON", "error");
      return;
    }

    setSaving(true);
    try {
      await adminApi.saveConfigSection(token, effectiveSection, parsed);
      toast(`Section "${effectiveSection}" saved`);
      loadStoredSections();
      loadLiveConfig();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleEditStored = (stored: StoredSection) => {
    // Check if the section name matches a known option
    const known = SECTION_OPTIONS.find((o) => o.value === stored.name);
    if (known) {
      setSection(stored.name);
    } else {
      setSection("_custom");
      setCustomSection(stored.name);
    }
    setJsonValue(JSON.stringify(stored.data, null, 2));
  };

  const handleDeleteStored = async (sectionName: string) => {
    try {
      await adminApi.deleteConfigSection(token, sectionName);
      toast(`Section "${sectionName}" deleted`);
      loadStoredSections();
      loadLiveConfig();
    } catch (e: any) {
      toast("Delete failed: " + e.message, "error");
    }
  };

  const toggleStoredExpand = (idx: number) => {
    setStoredSections((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, expanded: !s.expanded } : s)),
    );
  };

  const handleRefreshLive = async () => {
    try {
      const cfg = await adminApi.getLiveConfig(token);
      setLiveDisplay(JSON.stringify(cfg, null, 2));
      toast("Live config refreshed");
    } catch (e: any) {
      toast("Failed to refresh: " + e.message, "error");
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-[#eee] mb-4">Raw Configuration</h2>

      {/* Edit Config Section */}
      <Card title="Edit Config Section">
        <FormDropdown
          label="Section"
          value={section}
          onChange={setSection}
          options={SECTION_OPTIONS}
        />

        {section === "_custom" && (
          <FormInput
            label="Custom Section Name"
            value={customSection}
            onChange={setCustomSection}
            placeholder="my_custom_section"
          />
        )}

        <FormTextarea
          label="JSON Value"
          value={jsonValue}
          onChange={setJsonValue}
          placeholder='{"key": "value"}'
          large
        />

        <div className="flex items-center gap-2.5 mt-2">
          <button
            type="button"
            onClick={handleSaveSection}
            disabled={saving || !effectiveSection}
            className="px-4 py-2 bg-[#e94560] text-white rounded-md text-sm font-medium hover:bg-[#b83350] transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Saving..." : "Save Section"}
          </button>
          <button
            type="button"
            onClick={handleLoadCurrent}
            disabled={!effectiveSection}
            className="px-3 py-2 bg-[#0f3460] text-[#eee] border border-[#2a3a5c] rounded-md text-sm font-medium hover:border-[#e94560] transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Load Current
          </button>
        </div>
      </Card>

      {/* Stored Config Sections */}
      <Card title="Stored Config Sections">
        {storedLoading ? (
          <p className="text-[#999] text-sm">Loading...</p>
        ) : storedSections.length === 0 ? (
          <p className="text-[#999] text-sm">No stored config sections.</p>
        ) : (
          <div className="space-y-2">
            {storedSections.map((stored, idx) => (
              <div
                key={stored.name}
                className="bg-[#1a1a2e] border border-[#2a3a5c] rounded-md overflow-hidden"
              >
                {/* Section header */}
                <button
                  type="button"
                  onClick={() => toggleStoredExpand(idx)}
                  className="w-full flex items-center justify-between px-3 py-2.5 bg-transparent border-none cursor-pointer text-left"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block text-[#999] text-xs transition-transform"
                      style={{
                        transform: stored.expanded ? "rotate(90deg)" : "rotate(0deg)",
                      }}
                    >
                      &#9654;
                    </span>
                    <span className="text-sm font-mono text-[#eee]">{stored.name}</span>
                  </div>
                </button>

                {/* Section body */}
                {stored.expanded && (
                  <div className="px-3 pb-3 border-t border-[#2a3a5c]">
                    <pre className="text-xs text-[#999] font-mono bg-[#0d1117] rounded p-3 mt-2 overflow-x-auto whitespace-pre-wrap max-h-[300px] overflow-y-auto">
                      {JSON.stringify(stored.data, null, 2)}
                    </pre>
                    <div className="flex items-center gap-2 mt-2">
                      <button
                        type="button"
                        onClick={() => handleEditStored(stored)}
                        className="text-xs text-[#e94560] border border-[#e94560]/30 px-2.5 py-1 rounded hover:bg-[#e94560]/10 cursor-pointer transition-colors bg-transparent"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteStored(stored.name)}
                        className="text-xs text-[#c0392b] border border-[#c0392b]/30 px-2.5 py-1 rounded hover:bg-[#c0392b]/10 cursor-pointer transition-colors bg-transparent"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Live Merged Config */}
      <Card title="Live Merged Config">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-[#999]">
            Final merged configuration (file + DB overrides)
          </span>
          <button
            type="button"
            onClick={handleRefreshLive}
            className="text-xs text-[#999] border border-[#2a3a5c] px-2.5 py-1 rounded hover:border-[#e94560] hover:text-[#eee] cursor-pointer transition-colors bg-transparent"
          >
            Refresh
          </button>
        </div>
        <pre className="text-xs text-[#999] font-mono bg-[#0d1117] rounded p-3 overflow-x-auto whitespace-pre-wrap max-h-[500px] overflow-y-auto">
          {liveDisplay || "Loading..."}
        </pre>
      </Card>
    </div>
  );
}
