export type AgentStatus = "healthy" | "stale" | "offline" | "unknown";

export type GlobalFilters = {
  tenantId: string;
  environment: string;
  siteId: string;
  timeRange: string;
};

export type Agent = {
  agent_id: string;
  tenant_id: string;
  site_id: string;
  environment: string;
  host_name?: string | null;
  agent_version?: string | null;
  capabilities: string[];
  status: AgentStatus;
  created_at: number;
  last_seen_at?: number | null;
  certificate_fingerprint?: string | null;
  certificate_status?: string | null;
  telemetry_recent?: string;
  grafana_links?: GrafanaLinks;
};

export type GrafanaLinks = {
  grafana: string;
  logs: string;
  metrics: string;
  traces: string;
};

export type Host = {
  host_name: string;
  agent_id?: string | null;
  agent_status: AgentStatus;
  environment?: string | null;
  site_id?: string | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  filesystem_percent?: number | null;
  network_bytes_per_second?: number | null;
};

export type Overview = {
  agents: {
    total: number;
    healthy: number;
    stale: number;
    offline: number;
  };
  infrastructure: {
    host_count: number;
    cpu_percent?: number | null;
    memory_percent?: number | null;
    filesystem_percent?: number | null;
    network_bytes_per_second?: number | null;
    grafana_url?: string;
  };
  agents_by_version: Record<string, number>;
  agents_by_environment: Record<string, number>;
  agents_by_site: Record<string, number>;
  capabilities: Record<string, number>;
  recent_agent_activity: {
    agent_id: string;
    host_name?: string | null;
    status: AgentStatus;
    last_seen_at?: number | null;
  }[];
  platform_health: {
    agent_registry: string;
    prometheus: string;
  };
};

export type EnrollmentCredential = {
  enrollment_credential: string;
  one_time: boolean;
  site_id: string;
  environment: string;
  capabilities: string[];
  install_command: string;
  enrollment_command: string;
  start_command: string;
  verification_steps: string[];
};

export type SiteSummary = {
  site_id: string;
  environment: string;
  agent_count: number;
  healthy: number;
  stale: number;
  offline: number;
};

export type EnvironmentSummary = {
  environment: string;
  agent_count: number;
};

export type CapabilitySummary = {
  capability: string;
  agents: number;
};

export type Integration = {
  name: string;
  role: string;
  status: string;
  url?: string;
  reference?: string;
  actions?: { label: string; url: string }[];
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const OPERATOR_TOKEN_STORAGE_KEY = "observability.operatorToken";

export function getOperatorToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(OPERATOR_TOKEN_STORAGE_KEY) ?? "";
}

export function setOperatorToken(token: string) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(OPERATOR_TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(OPERATOR_TOKEN_STORAGE_KEY);
}

function headers(filters: GlobalFilters, json = false) {
  const token = getOperatorToken();
  return {
    ...(json ? { "content-type": "application/json" } : {}),
    ...(token ? { authorization: `Bearer ${token}` } : {}),
    "x-tenant-id": filters.tenantId
  };
}

function query(filters: GlobalFilters, extra: Record<string, string> = {}) {
  const params = new URLSearchParams();
  params.set("tenant_id", filters.tenantId);
  if (filters.environment) params.set("environment", filters.environment);
  if (filters.siteId) params.set("site_id", filters.siteId);
  for (const [key, value] of Object.entries(extra)) {
    if (value) params.set(key, value);
  }
  return params.toString();
}

async function request<T>(path: string, filters: GlobalFilters): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: headers(filters)
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function post<T>(path: string, filters: GlobalFilters, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: headers(filters, true),
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getOverview(filters: GlobalFilters) {
  return request<Overview>(`/v1/overview?${query(filters)}`, filters);
}

export function getAgents(filters: GlobalFilters, extra: Record<string, string> = {}) {
  return request<{ agents: Agent[] }>(`/v1/node-agents?${query(filters, extra)}`, filters);
}

export function getAgent(agentId: string, filters: GlobalFilters) {
  return request<Agent>(`/v1/node-agents/${encodeURIComponent(agentId)}?${query(filters)}`, filters);
}

export function getHosts(filters: GlobalFilters) {
  return request<{ hosts: Host[]; source: { available: boolean; errors: Record<string, string> } }>(
    `/v1/infrastructure/hosts?${query(filters)}`,
    filters
  );
}

export function getHost(hostName: string, filters: GlobalFilters) {
  return request<Host & { source: { available: boolean; errors: Record<string, string> } }>(
    `/v1/infrastructure/hosts/${encodeURIComponent(hostName)}?${query(filters)}`,
    filters
  );
}

export function createEnrollmentCredential(
  filters: GlobalFilters,
  payload: { site_id: string; environment: string; capabilities: string[]; host_name?: string }
) {
  return post<EnrollmentCredential>(`/v1/enrollment/credentials?${query(filters)}`, filters, payload);
}

export function getSites(filters: GlobalFilters) {
  return request<{ sites: SiteSummary[] }>(`/v1/sites?${query(filters)}`, filters);
}

export function getEnvironments(filters: GlobalFilters) {
  return request<{ environments: EnvironmentSummary[] }>(`/v1/environments?${query(filters)}`, filters);
}

export function getCapabilities(filters: GlobalFilters) {
  return request<{ capabilities: CapabilitySummary[] }>(`/v1/capabilities?${query(filters)}`, filters);
}

export function getIntegrations(filters: GlobalFilters) {
  return request<{ integrations: Integration[] }>(`/v1/integrations?${query(filters)}`, filters);
}
