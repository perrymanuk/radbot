import { useState, useEffect, useCallback } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  FormInput,
  FormToggle,
  ActionBar,
} from "@/components/admin/FormFields";
import * as adminApi from "@/lib/admin-api";

function formatSize(bytes: number): string {
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / (1024 ** 2)).toFixed(1)} MB`;
  return `${(bytes / (1024 ** 3)).toFixed(2)} GB`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function OllamaPanel() {
  const { loadLiveConfig, mergeConfigSection, toast, token } = useAdminStore();

  // Config state
  const [enabled, setEnabled] = useState(false);
  const [apiBase, setApiBase] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  // Models state
  const [models, setModels] = useState<adminApi.OllamaModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [pullModelName, setPullModelName] = useState("");
  const [pulling, setPulling] = useState(false);
  const [deletingModel, setDeletingModel] = useState<string | null>(null);

  // Load config
  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const ollama = cfg?.integrations?.ollama ?? {};
      setEnabled(ollama.enabled ?? false);
      setApiBase(ollama.api_base ?? "");
      setApiKey(ollama.api_key ? "***" : "");
    });
  }, []);

  // Load models
  const loadModels = useCallback(async () => {
    setLoadingModels(true);
    try {
      const data = await adminApi.listOllamaModels(token);
      setModels(data.models ?? []);
      if (data.error) {
        toast(data.error, "error");
      }
    } catch (e: any) {
      // Don't toast on initial load failure — server might not be configured
    } finally {
      setLoadingModels(false);
    }
  }, [token, toast]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, any> = {
        enabled,
        api_base: apiBase,
      };
      if (apiKey && apiKey !== "***") {
        payload.api_key = apiKey;
      }
      await mergeConfigSection("integrations", { ollama: payload });
      toast("Ollama settings saved");
      // Reload models with new config
      setTimeout(loadModels, 500);
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const body: Record<string, any> = { api_base: apiBase };
      if (apiKey && apiKey !== "***") {
        body.api_key = apiKey;
      }
      const resp = await fetch("/admin/api/test/ollama", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (data.status === "ok") {
        toast(data.message);
        loadModels();
      } else {
        toast(data.message, "error");
      }
    } catch (e: any) {
      toast("Test failed: " + e.message, "error");
    } finally {
      setTesting(false);
    }
  };

  const handlePull = async () => {
    if (!pullModelName.trim()) return;
    setPulling(true);
    try {
      const data = await adminApi.pullOllamaModel(token, pullModelName.trim());
      if (data.status === "ok") {
        toast(data.message);
        setPullModelName("");
        loadModels();
      } else {
        toast(data.message, "error");
      }
    } catch (e: any) {
      toast("Pull failed: " + e.message, "error");
    } finally {
      setPulling(false);
    }
  };

  const handleDelete = async (modelName: string) => {
    setDeletingModel(modelName);
    try {
      const data = await adminApi.deleteOllamaModel(token, modelName);
      if (data.status === "ok") {
        toast(data.message);
        loadModels();
      } else {
        toast(data.message, "error");
      }
    } catch (e: any) {
      toast("Delete failed: " + e.message, "error");
    } finally {
      setDeletingModel(null);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <h2 className="text-lg font-semibold mb-6">Ollama (Local LLM)</h2>

      <Card title="Connection Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="API Base URL"
          value={apiBase}
          onChange={setApiBase}
          placeholder="https://ollama.example.com"
        />
        <FormInput
          label="API Key"
          value={apiKey}
          onChange={setApiKey}
          placeholder="(optional, for authenticated servers)"
          type="password"
        />
        <ActionBar
          onSave={handleSave}
          saving={saving}
          onTest={handleTest}
          testing={testing}
        />
      </Card>

      <Card title="Downloaded Models">
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={pullModelName}
            onChange={(e) => setPullModelName(e.target.value)}
            placeholder="Model name (e.g. mistral-small3.2)"
            className="flex-1 p-2 border border-[#2a3a5c] rounded-md bg-[#1a1a2e] text-[#eee] text-sm outline-none focus:border-[#e94560]"
            onKeyDown={(e) => e.key === "Enter" && handlePull()}
          />
          <button
            onClick={handlePull}
            disabled={pulling || !pullModelName.trim()}
            className="px-4 py-2 bg-[#e94560] text-white rounded-md text-sm font-medium hover:bg-[#b83350] disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {pulling ? "Pulling..." : "Pull"}
          </button>
          <button
            onClick={loadModels}
            disabled={loadingModels}
            className="px-3 py-2 border border-[#2a3a5c] text-[#999] rounded-md text-sm hover:border-[#e94560] hover:text-[#eee] disabled:opacity-50 transition-colors cursor-pointer bg-transparent"
          >
            {loadingModels ? "..." : "Refresh"}
          </button>
        </div>

        {pulling && (
          <div className="text-[#e94560] text-sm mb-3">
            Pulling model... This may take several minutes for large models.
          </div>
        )}

        {models.length === 0 ? (
          <div className="text-[#666] text-sm py-4 text-center">
            {loadingModels ? "Loading..." : "No models downloaded"}
          </div>
        ) : (
          <div className="border border-[#2a3a5c] rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#0f3460] text-[#999] text-xs uppercase tracking-wider">
                  <th className="text-left py-2 px-3">Model</th>
                  <th className="text-right py-2 px-3">Size</th>
                  <th className="text-right py-2 px-3">Modified</th>
                  <th className="text-right py-2 px-3 w-16"></th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.name} className="border-t border-[#2a3a5c] hover:bg-[#0f3460]/30">
                    <td className="py-2 px-3 font-mono text-[#eee]">
                      <span>{m.name}</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(`ollama_chat/${m.name}`);
                          toast(`Copied ollama_chat/${m.name}`);
                        }}
                        className="ml-2 text-[#e94560] hover:text-[#ff6b81] text-xs cursor-pointer bg-transparent border-none"
                        title={`Copy ollama_chat/${m.name} to clipboard`}
                      >
                        Copy
                      </button>
                    </td>
                    <td className="py-2 px-3 text-right text-[#999]">{formatSize(m.size)}</td>
                    <td className="py-2 px-3 text-right text-[#999]">{formatDate(m.modified_at)}</td>
                    <td className="py-2 px-3 text-right">
                      <button
                        onClick={() => handleDelete(m.name)}
                        disabled={deletingModel === m.name}
                        className="text-[#c0392b] hover:text-[#e74c3c] text-xs disabled:opacity-50 cursor-pointer bg-transparent border-none"
                      >
                        {deletingModel === m.name ? "..." : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 text-[#666] text-xs leading-relaxed">
          <strong>Usage:</strong> Set agent models to <code className="text-[#999]">ollama_chat/model-name</code> in the
          Agent &amp; Models panel (e.g. <code className="text-[#999]">ollama_chat/mistral-small3.2</code>).
          <br />
          <strong>Note:</strong> search_agent (google_search grounding) and code_execution_agent (BuiltInCodeExecutor)
          require Gemini models and will not work with Ollama.
        </div>
      </Card>
    </div>
  );
}
