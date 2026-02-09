import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  FormInput,
  FormDropdown,
  FormTextarea,
  Card,
} from "@/components/admin/FormFields";

const CREDENTIAL_TYPE_OPTIONS = [
  { value: "api_key", label: "API Key" },
  { value: "oauth_token", label: "OAuth Token" },
  { value: "service_account", label: "Service Account" },
  { value: "oauth_client", label: "OAuth Client" },
];

export function CredentialsPanel() {
  const {
    credentials,
    credentialsLoading,
    loadCredentials,
    saveCredential,
    deleteCredential,
    toast,
  } = useAdminStore();

  // Store form state
  const [name, setName] = useState("");
  const [credType, setCredType] = useState("api_key");
  const [description, setDescription] = useState("");
  const [value, setValue] = useState("");

  useEffect(() => {
    loadCredentials();
  }, []);

  const handleStore = async () => {
    if (!name.trim()) {
      toast("Credential name is required", "error");
      return;
    }
    if (!value.trim()) {
      toast("Credential value is required", "error");
      return;
    }

    try {
      await saveCredential(name.trim(), value, credType, description || undefined);
      toast("Credential stored");
      setName("");
      setCredType("api_key");
      setDescription("");
      setValue("");
    } catch (e: any) {
      toast("Failed to store credential: " + e.message, "error");
    }
  };

  const handleDelete = async (credName: string) => {
    try {
      await deleteCredential(credName);
      toast("Credential deleted");
    } catch (e: any) {
      toast("Failed to delete credential: " + e.message, "error");
    }
  };

  // Filter out internal/config credentials
  const visibleCredentials = credentials.filter(
    (c) => c.credential_type !== "internal" && c.credential_type !== "config",
  );

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-lg font-semibold text-[#eee]">Credentials Store</h2>
        <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-[#1b3a1b] text-[#4caf50]">
          {visibleCredentials.length} stored
        </span>
      </div>

      {/* Store Credential Form */}
      <Card title="Store Credential">
        <FormInput
          label="Name"
          value={name}
          onChange={setName}
          placeholder="e.g. my_api_key"
        />
        <FormDropdown
          label="Type"
          value={credType}
          onChange={setCredType}
          options={CREDENTIAL_TYPE_OPTIONS}
        />
        <FormInput
          label="Description"
          value={description}
          onChange={setDescription}
          placeholder="Optional description"
        />
        <FormTextarea
          label="Value"
          value={value}
          onChange={setValue}
          placeholder="Secret value..."
        />
        <button
          type="button"
          onClick={handleStore}
          disabled={!name.trim() || !value.trim()}
          className="px-4 py-2 bg-[#e94560] text-white rounded-md text-sm font-medium hover:bg-[#b83350] transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          Store
        </button>
      </Card>

      {/* Stored Credentials Table */}
      <Card title="Stored Credentials">
        {credentialsLoading ? (
          <p className="text-[#999] text-sm">Loading...</p>
        ) : visibleCredentials.length === 0 ? (
          <p className="text-[#999] text-sm">No credentials stored yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[#2a3a5c]">
                  <th className="text-left py-2 px-3 text-xs text-[#999] font-medium">Name</th>
                  <th className="text-left py-2 px-3 text-xs text-[#999] font-medium">Type</th>
                  <th className="text-left py-2 px-3 text-xs text-[#999] font-medium">
                    Description
                  </th>
                  <th className="text-left py-2 px-3 text-xs text-[#999] font-medium">Updated</th>
                  <th className="text-right py-2 px-3 text-xs text-[#999] font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {visibleCredentials.map((cred) => (
                  <tr
                    key={cred.name}
                    className="border-b border-[#2a3a5c]/50 hover:bg-[#0f3460]/30 transition-colors"
                  >
                    <td className="py-2.5 px-3 font-mono text-[#eee]">{cred.name}</td>
                    <td className="py-2.5 px-3 text-[#999]">{cred.credential_type}</td>
                    <td className="py-2.5 px-3 text-[#999]">{cred.description || "--"}</td>
                    <td className="py-2.5 px-3 text-[#999]">
                      {cred.updated_at
                        ? new Date(cred.updated_at).toLocaleDateString([], {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })
                        : "--"}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleDelete(cred.name)}
                        className="text-xs text-[#c0392b] border border-[#c0392b]/30 px-2 py-1 rounded hover:bg-[#c0392b]/10 cursor-pointer transition-colors bg-transparent"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
