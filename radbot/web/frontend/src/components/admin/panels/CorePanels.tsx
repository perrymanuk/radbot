import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { useAppStore } from "@/stores/app-store";
import * as adminApi from "@/lib/admin-api";
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

const FALLBACK_MODELS = [
  "gemini-2.5-pro",
  "gemini-2.5-flash",
];

/** Shared hook: fetches available models from the API once per mount. */
function useModelOptions() {
  const { token } = useAdminStore();
  const [models, setModels] = useState<string[]>(FALLBACK_MODELS);

  useEffect(() => {
    if (!token) return;
    adminApi.listModels(token).then((m) => {
      if (m.length > 0) setModels(m);
    }).catch(() => {/* keep fallback */});
  }, [token]);

  return models;
}

// Sub-agent roster is pulled from /api/agent-info at runtime so the admin
// panel never drifts out of sync with the actual agent set. See
// radbot/web/api/agent_info.py::_enumerate_sub_agents.

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
        <h2 className="text-lg font-semibold text-txt-primary">Google API</h2>
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
  const modelOptions = useModelOptions();
  const agentInfo = useAppStore((s) => s.agentInfo);
  const loadAgentInfo = useAppStore((s) => s.loadAgentInfo);

  const subAgents = agentInfo?.sub_agents_detail ?? [];

  const [mainModel, setMainModel] = useState("");
  const [subAgentModel, setSubAgentModel] = useState("");
  const [googleCloudProject, setGoogleCloudProject] = useState("");
  const [enableSearch, setEnableSearch] = useState(false);
  const [enableCodeExec, setEnableCodeExec] = useState(false);
  const [sessionMode, setSessionMode] = useState(false);
  const [maxWorkers, setMaxWorkers] = useState("10");
  const [terseProtocolEnabled, setTerseProtocolEnabled] = useState(false);
  // Map of config_key ("casa_agent") → override string ("" = inherit default)
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig();
    // Agent info is loaded at app startup, but re-fetch here so the panel
    // always reflects the live roster if it's opened before that finishes.
    if (!agentInfo) loadAgentInfo();
  }, []);

  useEffect(() => {
    if (!liveConfig) return;
    const agent = liveConfig.agent || {};

    if (agent.main_model) setMainModel(agent.main_model);
    else if (agent.model) setMainModel(agent.model); // legacy fallback
    if (agent.sub_agent_model) setSubAgentModel(agent.sub_agent_model);
    if (agent.google_cloud_project !== undefined) setGoogleCloudProject(agent.google_cloud_project || "");
    if (agent.enable_adk_search !== undefined) setEnableSearch(!!agent.enable_adk_search);
    if (agent.enable_adk_code_execution !== undefined) setEnableCodeExec(!!agent.enable_adk_code_execution);
    if (agent.session_mode !== undefined) setSessionMode(agent.session_mode === "remote");
    if (agent.max_session_workers !== undefined) setMaxWorkers(String(agent.max_session_workers));
    if (agent.terse_protocol_enabled !== undefined) setTerseProtocolEnabled(!!agent.terse_protocol_enabled);

    const agentModels = agent.agent_models || {};
    const init: Record<string, string> = {};
    for (const sa of subAgents) {
      // Canonical key first, then legacy "<name>_agent_model" fallback.
      const legacy = sa.config_key.replace(/_agent$/, "") + "_agent_model";
      init[sa.config_key] = agentModels[sa.config_key] || agentModels[legacy] || "";
    }
    setOverrides(init);
  }, [liveConfig, subAgents.length]);

  const setOverride = (key: string, value: string) => {
    setOverrides((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Preserve any agent_models entries the runtime roster doesn't know about
      // (e.g. legacy agents or ones added after last page load). mergeConfigSection
      // deep-merges, so we only need to send the keys we're actively managing.
      const agentModels: Record<string, string> = {};
      for (const [k, v] of Object.entries(overrides)) {
        if (v.trim()) agentModels[k] = v.trim();
      }

      await mergeConfigSection("agent", {
        main_model: mainModel,
        sub_agent_model: subAgentModel,
        google_cloud_project: googleCloudProject || undefined,
        enable_adk_search: enableSearch,
        enable_adk_code_execution: enableCodeExec,
        session_mode: sessionMode ? "remote" : "local",
        max_session_workers: parseInt(maxWorkers, 10) || 10,
        terse_protocol_enabled: terseProtocolEnabled,
        agent_models: agentModels,
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
      <h2 className="text-lg font-semibold text-txt-primary mb-4">Agent Models</h2>

      <Card title="Agent Configuration">
        <FormRow>
          <FormInput
            label="Main Model"
            value={mainModel}
            onChange={setMainModel}
            placeholder="gemini-2.5-pro"
            datalist={modelOptions}
          />
          <FormInput
            label="Sub-Agent Default Model"
            value={subAgentModel}
            onChange={setSubAgentModel}
            placeholder="gemini-2.5-flash"
            datalist={modelOptions}
          />
        </FormRow>
        <FormInput
          label="Google Cloud Project ID"
          value={googleCloudProject}
          onChange={setGoogleCloudProject}
          placeholder="my-gcp-project"
        />
        <FormToggle label="Enable ADK Search" checked={enableSearch} onChange={setEnableSearch} />
        <FormToggle label="Enable ADK Code Execution" checked={enableCodeExec} onChange={setEnableCodeExec} />
      </Card>

      <Card title="Session Workers">
        <Note>
          When enabled, chat and terminal sessions run in separate Nomad worker containers that persist across main app restarts.
        </Note>
        <FormToggle label="Remote Session Mode" checked={sessionMode} onChange={setSessionMode} />
        {sessionMode && (
          <FormInput
            label="Max Concurrent Workers"
            value={maxWorkers}
            onChange={setMaxWorkers}
            placeholder="10"
          />
        )}
      </Card>

      <Card title="Sub-Agent Output">
        <Note>
          Terse JSON Protocol: casa, planner, comms, axel, and kidsvid emit compressed JSON
          (<code>summary</code> + <code>pass_through</code>) that Beto re-hydrates into prose.
          Reduces sub-agent output tokens. Env override:{" "}
          <code>RADBOT_TERSE_PROTOCOL_ENABLED</code>.
        </Note>
        <FormToggle
          label="Enable Terse JSON Protocol"
          checked={terseProtocolEnabled}
          onChange={setTerseProtocolEnabled}
        />
      </Card>

      {/* Collapsible Per-Agent Model Overrides */}
      <div className="mb-4">
        <button
          type="button"
          onClick={() => setOverridesOpen((v) => !v)}
          className="flex items-center gap-2 text-sm text-txt-secondary hover:text-txt-primary transition-colors cursor-pointer bg-transparent border-none p-0"
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
              Agents marked <em>gemini-only</em> use ADK built-ins (google_search, BuiltInCodeExecutor) that require Gemini.
            </Note>
            {subAgents.length === 0 ? (
              <div className="text-sm text-txt-secondary py-2">Loading sub-agent roster…</div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {subAgents.map((sa) => (
                  <FormInput
                    key={sa.config_key}
                    label={sa.gemini_only ? `${sa.name} (gemini-only)` : sa.name}
                    value={overrides[sa.config_key] || ""}
                    onChange={(v) => setOverride(sa.config_key, v)}
                    placeholder={sa.resolved_model ? `(default: ${sa.resolved_model})` : "(default)"}
                    datalist={modelOptions}
                  />
                ))}
              </div>
            )}
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
      <h2 className="text-lg font-semibold text-txt-primary mb-4">Web Server</h2>

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
      <h2 className="text-lg font-semibold text-txt-primary mb-4">Logging</h2>

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
