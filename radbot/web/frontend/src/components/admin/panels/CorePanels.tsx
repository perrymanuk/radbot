import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  FormInput,
  FormToggle,
  FormDropdown,
  FormTextarea,
  FormRow,
  Card,
  ActionBar,
  StatusBadge,
  Note,
} from "@/components/admin/FormFields";

const MODEL_OPTIONS = [
  "gemini-3-pro-preview",
  "gemini-2.5-pro",
  "gemini-2.5-flash",
  "gemini-2.0-flash",
  "gemini-2.0-flash-lite",
  "gemini-1.5-pro",
  "gemini-1.5-flash",
];

const OVERRIDE_AGENTS = [
  "search",
  "scout",
  "axel",
  "george",
  "memory",
  "todo",
  "calendar",
  "homeassistant",
  "gmail",
  "jira",
  "code_execution",
  "web_research",
  "filesystem",
] as const;

// ── GooglePanel ───────────────────────────────────────────────

export function GooglePanel() {
  const { liveConfig, loadLiveConfig, saveCredential, mergeConfigSection, testConnection, toast, status, loadStatus } =
    useAdminStore();

  const [apiKey, setApiKey] = useState("");
  const [useVertex, setUseVertex] = useState(false);
  const [vertexProject, setVertexProject] = useState("");
  const [vertexLocation, setVertexLocation] = useState("");
  const [serviceAccountJson, setServiceAccountJson] = useState("");

  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);

  useEffect(() => {
    loadLiveConfig();
    loadStatus();
  }, []);

  useEffect(() => {
    if (!liveConfig) return;
    const apiKeys = liveConfig.api_keys || {};
    const agent = liveConfig.agent || {};

    if (apiKeys.google) setApiKey(apiKeys.google);
    if (agent.use_vertex !== undefined) setUseVertex(!!agent.use_vertex);
    if (agent.vertex_project) setVertexProject(agent.vertex_project);
    if (agent.vertex_location) setVertexLocation(agent.vertex_location);
  }, [liveConfig]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const body: Record<string, any> = {};
      if (apiKey && !apiKey.startsWith("***")) {
        body.api_key = apiKey;
      }
      const result = await testConnection("google", body);
      setTestResult(result);
    } catch (e: any) {
      setTestResult({ status: "error", message: e.message });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save API key as credential (only if user changed it from masked value)
      if (apiKey && !apiKey.startsWith("***")) {
        await saveCredential("google_api_key", apiKey, "api_key", "Google API Key");
      }

      // Save service account JSON as credential if provided
      if (serviceAccountJson.trim()) {
        await saveCredential("google_service_account", serviceAccountJson.trim(), "service_account", "Google Service Account JSON");
      }

      // Save Vertex settings to agent config section
      await mergeConfigSection("agent", {
        use_vertex: useVertex,
        ...(useVertex
          ? {
              vertex_project: vertexProject,
              vertex_location: vertexLocation,
            }
          : {}),
      });

      toast("Google settings saved");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const googleStatus = status?.google?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-lg font-semibold text-[#eee]">Google API</h2>
        <StatusBadge status={googleStatus} />
      </div>

      <Card title="API Keys">
        <FormInput
          label="Google API Key"
          value={apiKey}
          onChange={setApiKey}
          type="password"
          placeholder="AIza..."
        />
      </Card>

      <Card title="Vertex AI">
        <FormToggle label="Use Vertex AI" checked={useVertex} onChange={setUseVertex} />
        {useVertex && (
          <>
            <FormInput
              label="Vertex Project ID"
              value={vertexProject}
              onChange={setVertexProject}
              placeholder="my-gcp-project"
            />
            <FormInput
              label="Vertex Location"
              value={vertexLocation}
              onChange={setVertexLocation}
              placeholder="us-central1"
            />
          </>
        )}
        <FormTextarea
          label="Service Account JSON"
          value={serviceAccountJson}
          onChange={setServiceAccountJson}
          placeholder='{"type": "service_account", ...}'
          large
        />
      </Card>

      <ActionBar
        onSave={handleSave}
        onTest={handleTest}
        testResult={testResult}
        testing={testing}
        saving={saving}
      />
    </div>
  );
}

// ── AgentModelsPanel ──────────────────────────────────────────

export function AgentModelsPanel() {
  const { liveConfig, loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [mainModel, setMainModel] = useState("");
  const [subAgentModel, setSubAgentModel] = useState("");
  const [enableSearch, setEnableSearch] = useState(false);
  const [enableCodeExec, setEnableCodeExec] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig();
  }, []);

  useEffect(() => {
    if (!liveConfig) return;
    const agent = liveConfig.agent || {};

    if (agent.model) setMainModel(agent.model);
    if (agent.sub_agent_model) setSubAgentModel(agent.sub_agent_model);
    if (agent.enable_adk_search !== undefined) setEnableSearch(!!agent.enable_adk_search);
    if (agent.enable_adk_code_execution !== undefined) setEnableCodeExec(!!agent.enable_adk_code_execution);

    const modelOverrides = agent.model_overrides || {};
    const init: Record<string, string> = {};
    for (const a of OVERRIDE_AGENTS) {
      init[a] = modelOverrides[a] || "";
    }
    setOverrides(init);
  }, [liveConfig]);

  const setOverride = (agent: string, value: string) => {
    setOverrides((prev) => ({ ...prev, [agent]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Build model_overrides, filtering out empty strings
      const modelOverrides: Record<string, string> = {};
      for (const [k, v] of Object.entries(overrides)) {
        if (v.trim()) modelOverrides[k] = v.trim();
      }

      await mergeConfigSection("agent", {
        model: mainModel,
        sub_agent_model: subAgentModel,
        enable_adk_search: enableSearch,
        enable_adk_code_execution: enableCodeExec,
        model_overrides: modelOverrides,
      });

      toast("Agent model settings saved");
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-[#eee] mb-4">Agent Models</h2>

      <Card title="Agent Configuration">
        <FormRow>
          <FormInput
            label="Main Model"
            value={mainModel}
            onChange={setMainModel}
            placeholder="gemini-2.5-pro"
            datalist={MODEL_OPTIONS}
          />
          <FormInput
            label="Sub-Agent Default Model"
            value={subAgentModel}
            onChange={setSubAgentModel}
            placeholder="gemini-2.0-flash"
            datalist={MODEL_OPTIONS}
          />
        </FormRow>
        <FormToggle label="Enable ADK Search" checked={enableSearch} onChange={setEnableSearch} />
        <FormToggle label="Enable ADK Code Execution" checked={enableCodeExec} onChange={setEnableCodeExec} />
      </Card>

      {/* Collapsible Per-Agent Model Overrides */}
      <div className="mb-4">
        <button
          type="button"
          onClick={() => setOverridesOpen((v) => !v)}
          className="flex items-center gap-2 text-sm text-[#999] hover:text-[#eee] transition-colors cursor-pointer bg-transparent border-none p-0"
        >
          <span
            className="inline-block transition-transform"
            style={{ transform: overridesOpen ? "rotate(90deg)" : "rotate(0deg)" }}
          >
            &#9654;
          </span>
          Per-Agent Model Overrides
        </button>

        {overridesOpen && (
          <Card>
            <Note>
              Leave blank to use the sub-agent default model. Override specific agents by entering a model name.
            </Note>
            <div className="grid grid-cols-2 gap-3">
              {OVERRIDE_AGENTS.map((agent) => (
                <FormInput
                  key={agent}
                  label={agent}
                  value={overrides[agent] || ""}
                  onChange={(v) => setOverride(agent, v)}
                  placeholder="(default)"
                  datalist={MODEL_OPTIONS}
                />
              ))}
            </div>
          </Card>
        )}
      </div>

      <ActionBar onSave={handleSave} saving={saving} />
    </div>
  );
}

// ── WebServerPanel ────────────────────────────────────────────

export function WebServerPanel() {
  const { liveConfig, loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [host, setHost] = useState("0.0.0.0");
  const [port, setPort] = useState("8000");
  const [debug, setDebug] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig();
  }, []);

  useEffect(() => {
    if (!liveConfig) return;
    const web = liveConfig.web || {};

    if (web.host !== undefined) setHost(web.host);
    if (web.port !== undefined) setPort(String(web.port));
    if (web.debug !== undefined) setDebug(!!web.debug);
  }, [liveConfig]);

  const handleSave = async () => {
    const portNum = parseInt(port, 10);
    if (isNaN(portNum) || portNum < 1 || portNum > 65535) {
      toast("Port must be between 1 and 65535", "error");
      return;
    }

    setSaving(true);
    try {
      await mergeConfigSection("web", {
        host,
        port: portNum,
        debug,
      });
      toast("Web server settings saved");
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-[#eee] mb-4">Web Server</h2>

      <Card title="Server Configuration">
        <FormRow>
          <FormInput
            label="Host"
            value={host}
            onChange={setHost}
            placeholder="0.0.0.0"
          />
          <FormInput
            label="Port"
            value={port}
            onChange={setPort}
            type="number"
            placeholder="8000"
          />
        </FormRow>
        <FormToggle label="Debug Mode" checked={debug} onChange={setDebug} />
      </Card>

      <ActionBar onSave={handleSave} saving={saving} />
    </div>
  );
}

// ── LoggingPanel ──────────────────────────────────────────────

const LOG_LEVELS = [
  { value: "DEBUG", label: "DEBUG" },
  { value: "INFO", label: "INFO" },
  { value: "WARNING", label: "WARNING" },
  { value: "ERROR", label: "ERROR" },
  { value: "CRITICAL", label: "CRITICAL" },
];

export function LoggingPanel() {
  const { liveConfig, loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [level, setLevel] = useState("INFO");
  const [format, setFormat] = useState("");
  const [logFile, setLogFile] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig();
  }, []);

  useEffect(() => {
    if (!liveConfig) return;
    const logging = liveConfig.logging || {};

    if (logging.level) setLevel(logging.level);
    if (logging.format !== undefined) setFormat(logging.format);
    if (logging.log_file !== undefined) setLogFile(logging.log_file);
  }, [liveConfig]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mergeConfigSection("logging", {
        level,
        format,
        log_file: logFile,
      });
      toast("Logging settings saved");
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-[#eee] mb-4">Logging</h2>

      <Card title="Logging Configuration">
        <FormDropdown
          label="Level"
          value={level}
          onChange={setLevel}
          options={LOG_LEVELS}
        />
        <FormInput
          label="Format"
          value={format}
          onChange={setFormat}
          placeholder="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        />
        <FormInput
          label="Log File"
          value={logFile}
          onChange={setLogFile}
          placeholder="/var/log/radbot/app.log"
        />
      </Card>

      <ActionBar onSave={handleSave} saving={saving} />
    </div>
  );
}
