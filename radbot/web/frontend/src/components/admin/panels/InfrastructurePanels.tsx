import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  Note,
  FormInput,
  FormRow,
  FormToggle,
  ActionBar,
  StatusBadge,
} from "@/components/admin/FormFields";
import type { TestResult } from "@/lib/admin-api";

// ── PostgreSQL Panel ──────────────────────────────────────
export function PostgresqlPanel() {
  const { liveConfig, loadLiveConfig, status } = useAdminStore();

  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [user, setUser] = useState("");
  const [password] = useState("***");
  const [dbName, setDbName] = useState("");

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const db = cfg?.database ?? {};
      setHost(db.host ?? "");
      setPort(db.port != null ? String(db.port) : "");
      setUser(db.user ?? "");
      setDbName(db.db_name ?? "");
    });
  }, []);

  const pgStatus = status?.postgresql?.status;

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-lg font-semibold">PostgreSQL</h2>
        {pgStatus && <StatusBadge status={pgStatus} />}
      </div>

      <Note>
        Database settings are bootstrap config and cannot be changed here.
      </Note>

      <Card title="Connection Settings">
        <FormInput label="Host" value={host} onChange={() => {}} readOnly />
        <FormRow>
          <FormInput label="Port" value={port} onChange={() => {}} readOnly />
          <FormInput label="User" value={user} onChange={() => {}} readOnly />
        </FormRow>
        <FormInput
          label="Password"
          value={password}
          onChange={() => {}}
          type="password"
          readOnly
        />
        <FormInput label="Database" value={dbName} onChange={() => {}} readOnly />
      </Card>
    </div>
  );
}

// ── Qdrant Panel ──────────────────────────────────────────
export function QdrantPanel() {
  const {
    liveConfig,
    loadLiveConfig,
    status,
    saveCredential,
    saveConfigSection,
    testConnection,
    toast,
  } = useAdminStore();

  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("***");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [collection, setCollection] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const vdb = cfg?.vector_db ?? {};
      setUrl(vdb.url ?? "");
      setHost(vdb.host ?? "");
      setPort(vdb.port != null ? String(vdb.port) : "");
      setCollection(vdb.collection ?? "");
    });
  }, []);

  const qdrantStatus = status?.qdrant?.status;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testConnection("qdrant", {
        url,
        api_key: apiKey === "***" ? undefined : apiKey,
        host,
        port: port ? parseInt(port, 10) : undefined,
      });
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
      if (apiKey && apiKey !== "***") {
        await saveCredential("qdrant_api_key", apiKey, "api_key", "Qdrant API key");
      }
      await saveConfigSection("vector_db", {
        url,
        host,
        port: port ? parseInt(port, 10) : undefined,
        collection,
      });
      toast("Qdrant settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-lg font-semibold">Qdrant</h2>
        {qdrantStatus && <StatusBadge status={qdrantStatus} />}
      </div>

      <Card title="Connection Settings">
        <FormInput
          label="URL"
          value={url}
          onChange={setUrl}
          placeholder="http://localhost:6333"
        />
        <FormInput
          label="API Key"
          value={apiKey}
          onChange={setApiKey}
          type="password"
        />
        <FormRow>
          <FormInput
            label="Host (alternative)"
            value={host}
            onChange={setHost}
          />
          <FormInput
            label="Port"
            value={port}
            onChange={setPort}
            type="number"
          />
        </FormRow>
        <FormInput
          label="Collection"
          value={collection}
          onChange={setCollection}
        />
        <ActionBar
          onTest={handleTest}
          onSave={handleSave}
          testResult={testResult}
          testing={testing}
          saving={saving}
        />
      </Card>
    </div>
  );
}

// ── Redis Panel ───────────────────────────────────────────
export function RedisPanel() {
  const {
    liveConfig,
    loadLiveConfig,
    status,
    mergeConfigSection,
    testConnection,
    toast,
  } = useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [ttl, setTtl] = useState("300");
  const [maxSize, setMaxSize] = useState("1000");
  const [selectiveCaching, setSelectiveCaching] = useState(false);
  const [minTokens, setMinTokens] = useState("0");
  const [redisUrl, setRedisUrl] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const cache = cfg?.cache ?? {};
      setEnabled(cache.enabled ?? false);
      setTtl(cache.ttl != null ? String(cache.ttl) : "300");
      setMaxSize(cache.max_size != null ? String(cache.max_size) : "1000");
      setSelectiveCaching(cache.selective_caching ?? false);
      setMinTokens(cache.min_tokens != null ? String(cache.min_tokens) : "0");
      setRedisUrl(cache.redis_url ?? "");
    });
  }, []);

  const redisStatus = status?.redis?.status;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testConnection("redis", {
        redis_url: redisUrl,
      });
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
      await mergeConfigSection("cache", {
        enabled,
        ttl: parseInt(ttl, 10),
        max_size: parseInt(maxSize, 10),
        selective_caching: selectiveCaching,
        min_tokens: parseInt(minTokens, 10),
        redis_url: redisUrl,
      });
      toast("Redis / cache settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-lg font-semibold">Redis / Cache</h2>
        {redisStatus && <StatusBadge status={redisStatus} />}
      </div>

      <Card title="Cache Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormRow>
          <FormInput
            label="TTL (seconds)"
            value={ttl}
            onChange={setTtl}
            type="number"
          />
          <FormInput
            label="Max Size"
            value={maxSize}
            onChange={setMaxSize}
            type="number"
          />
        </FormRow>
        <FormToggle
          label="Selective Caching"
          checked={selectiveCaching}
          onChange={setSelectiveCaching}
        />
        <FormInput
          label="Min Tokens"
          value={minTokens}
          onChange={setMinTokens}
          type="number"
        />
        <FormInput
          label="Redis URL"
          value={redisUrl}
          onChange={setRedisUrl}
          placeholder="redis://localhost:6379/0"
        />
        <ActionBar
          onTest={handleTest}
          onSave={handleSave}
          testResult={testResult}
          testing={testing}
          saving={saving}
        />
      </Card>
    </div>
  );
}
