import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  FormInput,
  FormToggle,
  FormDropdown,
  FormRow,
  Card,
  ActionBar,
  Note,
} from "@/components/admin/FormFields";

interface MCPServer {
  id: string;
  name: string;
  enabled: boolean;
  transport: string;
  url: string;
  command: string;
  args: string;
  auth_type: string;
  auth_token: string;
  timeout: number;
  retry_max_attempts: number;
  retry_backoff: number;
}

const TRANSPORT_OPTIONS = [
  { value: "sse", label: "SSE" },
  { value: "websocket", label: "WebSocket" },
  { value: "http", label: "HTTP" },
  { value: "stdio", label: "Stdio" },
];

const AUTH_TYPE_OPTIONS = [
  { value: "none", label: "None" },
  { value: "token", label: "Token" },
  { value: "basic", label: "Basic" },
];

function defaultServer(): MCPServer {
  return {
    id: `mcp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    name: "New Server",
    enabled: true,
    transport: "sse",
    url: "",
    command: "",
    args: "",
    auth_type: "none",
    auth_token: "",
    timeout: 30,
    retry_max_attempts: 3,
    retry_backoff: 1,
  };
}

export function MCPServersPanel() {
  const { liveConfig, loadLiveConfig, mergeConfigSection, saveCredential, toast } =
    useAdminStore();

  const [servers, setServers] = useState<MCPServer[]>([]);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig();
  }, []);

  useEffect(() => {
    if (!liveConfig) return;
    const mcp = liveConfig.integrations?.mcp || {};
    const serverList = mcp.servers || [];

    const loaded: MCPServer[] = serverList.map((s: any) => ({
      id: s.id || `mcp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      name: s.name || "Unnamed",
      enabled: s.enabled !== undefined ? !!s.enabled : true,
      transport: s.transport || "sse",
      url: s.url || "",
      command: s.command || "",
      args: Array.isArray(s.args) ? s.args.join(", ") : s.args || "",
      auth_type: s.auth_type || "none",
      auth_token: s.auth_token || "",
      timeout: s.timeout ?? 30,
      retry_max_attempts: s.retry_max_attempts ?? 3,
      retry_backoff: s.retry_backoff ?? 1,
    }));

    setServers(loaded);
  }, [liveConfig]);

  const updateServer = (idx: number, field: keyof MCPServer, value: any) => {
    setServers((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], [field]: value };
      return copy;
    });
  };

  const deleteServer = (idx: number) => {
    setServers((prev) => prev.filter((_, i) => i !== idx));
    if (expandedIdx === idx) {
      setExpandedIdx(null);
    } else if (expandedIdx !== null && expandedIdx > idx) {
      setExpandedIdx(expandedIdx - 1);
    }
  };

  const addServer = () => {
    setServers((prev) => [...prev, defaultServer()]);
    setExpandedIdx(servers.length);
  };

  const toggleExpand = (idx: number) => {
    setExpandedIdx((prev) => (prev === idx ? null : idx));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save auth tokens as credentials, then strip from config
      const configServers = [];
      for (const server of servers) {
        const cfg: Record<string, any> = {
          id: server.id,
          name: server.name,
          enabled: server.enabled,
          transport: server.transport,
          url: server.url,
          command: server.command,
          args: server.args
            .split(",")
            .map((a) => a.trim())
            .filter(Boolean),
          auth_type: server.auth_type,
          timeout: server.timeout,
          retry_max_attempts: server.retry_max_attempts,
          retry_backoff: server.retry_backoff,
        };

        // Save auth token as credential if changed
        if (server.auth_token && !server.auth_token.startsWith("***")) {
          await saveCredential(
            `mcp_${server.id}_auth_token`,
            server.auth_token,
            "api_key",
            `MCP auth token for ${server.name}`,
          );
        }
        // Do not include auth_token in config
        configServers.push(cfg);
      }

      await mergeConfigSection("integrations", {
        mcp: { servers: configServers },
      });

      toast("MCP server configuration saved");
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-[#eee] mb-4">MCP Servers</h2>

      <Note>
        Configure Model Context Protocol servers. Auth tokens are stored separately as encrypted
        credentials and will not appear in the config file.
      </Note>

      {servers.length === 0 && (
        <p className="text-[#999] text-sm mb-4">
          No MCP servers configured. Click "Add Server" to get started.
        </p>
      )}

      {servers.map((server, idx) => (
        <div
          key={server.id}
          className="bg-[#16213e] border border-[#2a3a5c] rounded-lg mb-3 overflow-hidden"
        >
          {/* Header */}
          <button
            type="button"
            onClick={() => toggleExpand(idx)}
            className="w-full flex items-center justify-between px-4 py-3 bg-transparent border-none cursor-pointer text-left"
          >
            <div className="flex items-center gap-2.5">
              <span
                className="inline-block text-[#999] text-xs transition-transform"
                style={{
                  transform: expandedIdx === idx ? "rotate(90deg)" : "rotate(0deg)",
                }}
              >
                &#9654;
              </span>
              <span className="text-sm font-medium text-[#eee]">{server.name || "Unnamed"}</span>
              <span className="text-xs text-[#666]">({server.transport})</span>
              {!server.enabled && (
                <span className="text-[0.65rem] px-1.5 py-0.5 rounded bg-[#2a2a2a] text-[#666]">
                  disabled
                </span>
              )}
            </div>
          </button>

          {/* Body */}
          {expandedIdx === idx && (
            <div className="px-4 pb-4 border-t border-[#2a3a5c]">
              <div className="pt-3">
                <FormRow>
                  <FormInput
                    label="Server ID"
                    value={server.id}
                    onChange={(v) => updateServer(idx, "id", v)}
                    placeholder="unique-server-id"
                  />
                  <FormInput
                    label="Name"
                    value={server.name}
                    onChange={(v) => updateServer(idx, "name", v)}
                    placeholder="My MCP Server"
                  />
                </FormRow>

                <FormToggle
                  label="Enabled"
                  checked={server.enabled}
                  onChange={(v) => updateServer(idx, "enabled", v)}
                />

                <FormDropdown
                  label="Transport"
                  value={server.transport}
                  onChange={(v) => updateServer(idx, "transport", v)}
                  options={TRANSPORT_OPTIONS}
                />

                {server.transport !== "stdio" && (
                  <FormInput
                    label="URL"
                    value={server.url}
                    onChange={(v) => updateServer(idx, "url", v)}
                    placeholder="http://localhost:3000/mcp"
                  />
                )}

                {server.transport === "stdio" && (
                  <>
                    <FormInput
                      label="Command"
                      value={server.command}
                      onChange={(v) => updateServer(idx, "command", v)}
                      placeholder="/usr/local/bin/mcp-server"
                    />
                    <FormInput
                      label="Arguments (comma-separated)"
                      value={server.args}
                      onChange={(v) => updateServer(idx, "args", v)}
                      placeholder="--port, 3000, --verbose"
                      hint="Separate arguments with commas"
                    />
                  </>
                )}

                <FormRow>
                  <FormDropdown
                    label="Auth Type"
                    value={server.auth_type}
                    onChange={(v) => updateServer(idx, "auth_type", v)}
                    options={AUTH_TYPE_OPTIONS}
                  />
                  {server.auth_type !== "none" && (
                    <FormInput
                      label="Auth Token"
                      value={server.auth_token}
                      onChange={(v) => updateServer(idx, "auth_token", v)}
                      type="password"
                      placeholder="Token or password"
                    />
                  )}
                </FormRow>

                <FormRow cols={3}>
                  <FormInput
                    label="Timeout (sec)"
                    value={server.timeout}
                    onChange={(v) => updateServer(idx, "timeout", parseInt(v, 10) || 0)}
                    type="number"
                  />
                  <FormInput
                    label="Retry Max Attempts"
                    value={server.retry_max_attempts}
                    onChange={(v) => updateServer(idx, "retry_max_attempts", parseInt(v, 10) || 0)}
                    type="number"
                  />
                  <FormInput
                    label="Retry Backoff (sec)"
                    value={server.retry_backoff}
                    onChange={(v) => updateServer(idx, "retry_backoff", parseFloat(v) || 0)}
                    type="number"
                  />
                </FormRow>

                <div className="mt-3 pt-3 border-t border-[#2a3a5c]">
                  <button
                    type="button"
                    onClick={() => deleteServer(idx)}
                    className="text-xs text-[#c0392b] border border-[#c0392b]/30 px-3 py-1.5 rounded hover:bg-[#c0392b]/10 cursor-pointer transition-colors bg-transparent"
                  >
                    Delete Server
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      ))}

      <button
        type="button"
        onClick={addServer}
        className="w-full py-2.5 border border-dashed border-[#2a3a5c] rounded-lg text-sm text-[#999] hover:border-[#e94560] hover:text-[#eee] transition-colors cursor-pointer bg-transparent mb-4"
      >
        + Add Server
      </button>

      <ActionBar onSave={handleSave} saving={saving} />
    </div>
  );
}
