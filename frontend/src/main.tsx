import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Agent,
  AgentStatus,
  CapabilitySummary,
  EnvironmentSummary,
  GlobalFilters,
  Host,
  Integration,
  Overview,
  SiteSummary,
  createEnrollmentCredential,
  getAgent,
  getAgents,
  getCapabilities,
  getEnvironments,
  getHost,
  getHosts,
  getIntegrations,
  getOverview,
  getOperatorToken,
  getSites,
  setOperatorToken
} from "./api";
import "./styles.css";

type Page = "overview" | "agents" | "enrollment" | "sites" | "environments" | "capabilities" | "integrations" | "settings";

const NAV: { id: Page; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "agents", label: "Agents" },
  { id: "enrollment", label: "Enrollment" },
  { id: "sites", label: "Sites" },
  { id: "environments", label: "Environments" },
  { id: "capabilities", label: "Capabilities" },
  { id: "integrations", label: "Integrations" },
  { id: "settings", label: "Settings" }
];

const DEFAULT_FILTERS: GlobalFilters = {
  tenantId: "tenant-a",
  environment: "",
  siteId: "",
  timeRange: "1h"
};

const CAPABILITY_OPTIONS = ["otlp", "docker", "filelog", "hostmetrics", "prometheus"];
const ENVIRONMENT_OPTIONS = ["production", "staging", "development", "validation"];

function App() {
  const [page, setPage] = useState<Page>("overview");
  const [filters, setFilters] = useState<GlobalFilters>(DEFAULT_FILTERS);
  const [health, setHealth] = useState<AgentStatus>("unknown");

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">OP</span>
          <div>
            <strong>Platform</strong>
            <small>Management Console</small>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <button className={page === item.id ? "active" : ""} key={item.id} onClick={() => setPage(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="main">
        <TopBar filters={filters} onChange={setFilters} health={health} />
        {page === "overview" && <OverviewPage filters={filters} onHealth={setHealth} onNavigate={setPage} />}
        {page === "agents" && <AgentsPage filters={filters} />}
        {page === "enrollment" && <EnrollmentPage filters={filters} />}
        {page === "sites" && <SitesPage filters={filters} onNavigate={setPage} onFilter={setFilters} />}
        {page === "environments" && <EnvironmentsPage filters={filters} onNavigate={setPage} onFilter={setFilters} />}
        {page === "capabilities" && <CapabilitiesPage filters={filters} onNavigate={setPage} />}
        {page === "integrations" && <IntegrationsPage filters={filters} />}
        {page === "settings" && (
          <PlaceholderPage title="Settings" text="Tenant configuration, authentication, notifications, agent defaults, retention, and integration settings will appear here in future milestones." />
        )}
      </main>
    </div>
  );
}

function TopBar({ filters, onChange, health }: { filters: GlobalFilters; onChange: (filters: GlobalFilters) => void; health: AgentStatus }) {
  const [operatorToken, updateOperatorToken] = useState(() => getOperatorToken());

  function saveOperatorToken(value: string) {
    updateOperatorToken(value);
    setOperatorToken(value);
  }

  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Manage</p>
        <h1>Observability fleet</h1>
      </div>
      <div className="filters">
        <label>
          Tenant
          <input value={filters.tenantId} onChange={(event) => onChange({ ...filters, tenantId: event.target.value })} />
        </label>
        <label>
          Environment
          <input placeholder="All" value={filters.environment} onChange={(event) => onChange({ ...filters, environment: event.target.value })} />
        </label>
        <label>
          Site
          <input placeholder="All" value={filters.siteId} onChange={(event) => onChange({ ...filters, siteId: event.target.value })} />
        </label>
        <label>
          Time range
          <select value={filters.timeRange} onChange={(event) => onChange({ ...filters, timeRange: event.target.value })}>
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="6h">6h</option>
            <option value="24h">24h</option>
          </select>
        </label>
        <label>
          Operator token
          <input type="password" placeholder="Required in production" value={operatorToken} onChange={(event) => saveOperatorToken(event.target.value)} />
        </label>
        <StatusBadge status={health} label={health === "unknown" ? "No fleet data" : `${health} fleet`} />
      </div>
    </header>
  );
}

function OverviewPage({ filters, onHealth, onNavigate }: { filters: GlobalFilters; onHealth: (status: AgentStatus) => void; onNavigate: (page: Page) => void }) {
  const { data, loading, error } = useResource(() => getOverview(filters), [filters]);

  useEffect(() => {
    if (!data) return;
    if (data.agents.offline > 0) onHealth("offline");
    else if (data.agents.stale > 0) onHealth("stale");
    else if (data.agents.healthy > 0) onHealth("healthy");
    else onHealth("unknown");
  }, [data, onHealth]);

  if (loading) return <LoadingState title="Loading fleet overview" />;
  if (error) return <ErrorState title="Overview unavailable" detail={error.message} />;
  if (!data) return <EmptyState title="No fleet data" text="Generate an enrollment credential and enroll a Node Agent to begin." />;

  return (
    <section className="page">
      <PageHeader title="Overview" description="Fleet health for agents, sites, environments, capabilities, and platform integrations." />
      <div className="card-grid four">
        <MetricCard label="Total agents" value={data.agents.total} />
        <MetricCard label="Healthy" value={data.agents.healthy} tone="good" />
        <MetricCard label="Stale" value={data.agents.stale} tone="warn" />
        <MetricCard label="Offline" value={data.agents.offline} tone="bad" />
      </div>
      <div className="card-grid">
        <SummaryPanel title="Agents by version">
          <Distribution data={data.agents_by_version} empty="No agent versions reported yet." />
        </SummaryPanel>
        <SummaryPanel title="Agents by environment">
          <Distribution data={data.agents_by_environment} empty="No environments have agents yet." />
        </SummaryPanel>
        <SummaryPanel title="Agents by site">
          <Distribution data={data.agents_by_site} empty="No sites have agents yet." />
        </SummaryPanel>
      </div>
      <div className="card-grid">
        <SummaryPanel title="Capabilities distribution">
          <Distribution data={data.capabilities} empty="No capabilities reported yet." />
        </SummaryPanel>
        <SummaryPanel title="Recent agent activity">
          {data.recent_agent_activity.length === 0 ? (
            <Unavailable text="No heartbeats have been observed yet." />
          ) : (
            <MetricRows rows={data.recent_agent_activity.map((agent) => [agent.host_name ?? agent.agent_id, formatTime(agent.last_seen_at)])} />
          )}
        </SummaryPanel>
        <SummaryPanel title="Platform health">
          <MetricRows rows={[["Agent Registry", data.platform_health.agent_registry], ["Prometheus", data.platform_health.prometheus]]} />
          <div className="action-row">
            <button onClick={() => onNavigate("integrations")}>View integrations</button>
            {data.infrastructure.grafana_url && <a href={data.infrastructure.grafana_url} target="_blank" rel="noreferrer">Open Grafana metrics</a>}
          </div>
        </SummaryPanel>
      </div>
    </section>
  );
}

function AgentsPage({ filters }: { filters: GlobalFilters }) {
  const [status, setStatus] = useState("");
  const [capability, setCapability] = useState("");
  const [version, setVersion] = useState("");
  const { data, loading, error } = useResource(() => getAgents(filters, { status }), [filters, status]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const agents = useMemo(() => {
    const list = data?.agents ?? [];
    return list.filter((agent) => {
      const matchesCapability = capability ? agent.capabilities.includes(capability) : true;
      const matchesVersion = version ? (agent.agent_version ?? "").includes(version) : true;
      return matchesCapability && matchesVersion;
    });
  }, [data, capability, version]);

  useEffect(() => setSelectedId(null), [filters]);

  return (
    <section className="page">
      <PageHeader title="Agents" description="Manage Node Agent identity, health, runtime, capabilities, and certificate state." />
      <FilterBar>
        <Select label="Status" value={status} onChange={setStatus} options={["", "healthy", "stale", "offline"]} />
        <TextFilter label="Capability" value={capability} onChange={setCapability} placeholder="hostmetrics" />
        <TextFilter label="Version" value={version} onChange={setVersion} placeholder="1.1.0" />
      </FilterBar>
      {loading && <LoadingState title="Loading agents" />}
      {error && <ErrorState title="Agents unavailable" detail={error.message} />}
      {!loading && !error && agents.length === 0 && <EmptyState title="No agents found" text="Try a different filter or create an enrollment credential for a new Node Agent." />}
      {agents.length > 0 && (
        <div className="split">
          <DataTable
            columns={["Agent", "Agent ID", "Status", "Version", "Environment", "Site", "Last Seen", "Capabilities", "Certificate"]}
            rows={agents.map((agent) => [
              <button className="link-button" onClick={() => setSelectedId(agent.agent_id)}>{agent.host_name ?? agent.agent_id}</button>,
              agent.agent_id,
              <StatusBadge status={agent.status} />,
              agent.agent_version ?? "Unknown",
              agent.environment,
              agent.site_id,
              formatTime(agent.last_seen_at),
              agent.capabilities.join(", ") || "None reported",
              agent.certificate_status ?? "Unknown"
            ])}
          />
          <AgentDetail selectedId={selectedId ?? agents[0].agent_id} filters={filters} />
        </div>
      )}
    </section>
  );
}

function AgentDetail({ selectedId, filters }: { selectedId: string; filters: GlobalFilters }) {
  const { data, loading, error } = useResource(() => getAgent(selectedId, filters), [selectedId, filters]);
  const host = data?.host_name;
  const hostMetrics = useResource(() => (host ? getHost(host, filters) : Promise.resolve(null)), [host, filters]);

  if (loading) return <LoadingState title="Loading agent detail" compact />;
  if (error) return <ErrorState title="Agent detail unavailable" detail={error.message} compact />;
  if (!data) return null;

  return (
    <aside className="detail-panel">
      <h3>{data.host_name ?? "Agent detail"}</h3>
      <StatusBadge status={data.status} />
      <SectionTitle title="Identity" />
      <MetricRows rows={[["Agent ID", data.agent_id], ["Tenant", data.tenant_id], ["Site", data.site_id], ["Environment", data.environment], ["Hostname", data.host_name ?? "Unknown"]]} />
      <SectionTitle title="Health" />
      <MetricRows rows={[["Status", data.status], ["Last seen", formatTime(data.last_seen_at)], ["Heartbeat", data.last_seen_at ? "Observed" : "Not observed"]]} />
      <SectionTitle title="Runtime" />
      <MetricRows rows={[["Version", data.agent_version ?? "Unknown"], ["Capabilities", data.capabilities.join(", ") || "None reported"]]} />
      <SectionTitle title="Security" />
      <MetricRows rows={[["Certificate", data.certificate_status ?? "Unknown"], ["Fingerprint", shorten(data.certificate_fingerprint)]]} />
      <SectionTitle title="Grafana" />
      <ActionLinks links={[
        ["View Logs", data.grafana_links?.logs],
        ["View Metrics", data.grafana_links?.metrics],
        ["View Traces", data.grafana_links?.traces]
      ]} />
      <SectionTitle title="Associated infrastructure" />
      {hostMetrics.loading && <LoadingState title="Loading host association" compact />}
      {hostMetrics.error && <Unavailable text="Host association is unavailable." />}
      {hostMetrics.data && <MetricRows rows={[["CPU", formatPercent(hostMetrics.data.cpu_percent)], ["Memory", formatPercent(hostMetrics.data.memory_percent)], ["Filesystem", formatPercent(hostMetrics.data.filesystem_percent)], ["Network", formatBytes(hostMetrics.data.network_bytes_per_second)]]} />}
    </aside>
  );
}

function EnrollmentPage({ filters }: { filters: GlobalFilters }) {
  const [siteId, setSiteId] = useState(filters.siteId || "site-1");
  const [environment, setEnvironment] = useState(filters.environment || "validation");
  const [hostName, setHostName] = useState("");
  const [capabilities, setCapabilities] = useState<string[]>(["otlp", "hostmetrics"]);
  const [result, setResult] = useState<Awaited<ReturnType<typeof createEnrollmentCredential>> | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const credential = await createEnrollmentCredential(filters, { site_id: siteId, environment, capabilities, host_name: hostName || undefined });
      setResult(credential);
    } catch (reason) {
      setError(reason as Error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page">
      <PageHeader title="Enrollment" description="Create a one-time credential and guide a new Node Agent through install, enroll, and start." />
      <div className="card-grid two-one">
        <SummaryPanel title="Enroll new agent">
          <div className="form-stack">
            <TextFilter label="Site" value={siteId} onChange={setSiteId} placeholder="site-1" />
            <Select label="Environment" value={environment} onChange={setEnvironment} options={ENVIRONMENT_OPTIONS} />
            <TextFilter label="Expected hostname" value={hostName} onChange={setHostName} placeholder="prod-web-01" />
            <CapabilityPicker selected={capabilities} onChange={setCapabilities} />
            <button disabled={loading} onClick={generate}>{loading ? "Generating..." : "Generate enrollment credential"}</button>
            {error && <ErrorState title="Credential generation failed" detail={error.message} compact />}
          </div>
        </SummaryPanel>
        <SummaryPanel title="Workflow">
          <ol className="steps"><li>Select site and environment.</li><li>Generate a one-time enrollment credential.</li><li>Install the Node Agent package.</li><li>Run enrollment on the node.</li><li>Start the Agent and confirm it appears healthy.</li></ol>
        </SummaryPanel>
      </div>
      {result && (
        <SummaryPanel title="Enrollment instructions">
          <p className="sensitive-note">This credential is shown once. Store it securely and do not reuse it after enrollment.</p>
          <CommandBlock label="Credential" value={result.enrollment_credential} />
          <CommandBlock label="Install" value={result.install_command} />
          <CommandBlock label="Enroll" value={result.enrollment_command} />
          <CommandBlock label="Start" value={result.start_command} />
          <SectionTitle title="Verification" />
          <ol className="steps">{result.verification_steps.map((step) => <li key={step}>{step}</li>)}</ol>
        </SummaryPanel>
      )}
    </section>
  );
}

function SitesPage({ filters, onNavigate, onFilter }: { filters: GlobalFilters; onNavigate: (page: Page) => void; onFilter: (filters: GlobalFilters) => void }) {
  const { data, loading, error } = useResource(() => getSites(filters), [filters]);
  return <SummaryListPage title="Sites" description="Sites are derived from enrolled Agent identity for this MVP." loading={loading} error={error} empty="No sites have enrolled agents yet." table={data?.sites.map((site: SiteSummary) => [<button className="link-button" onClick={() => { onFilter({ ...filters, siteId: site.site_id, environment: site.environment }); onNavigate("agents"); }}>{site.site_id}</button>, site.environment, site.agent_count, site.healthy, site.stale, site.offline])} columns={["Site", "Environment", "Agents", "Healthy", "Stale", "Offline"]} />;
}

function EnvironmentsPage({ filters, onNavigate, onFilter }: { filters: GlobalFilters; onNavigate: (page: Page) => void; onFilter: (filters: GlobalFilters) => void }) {
  const { data, loading, error } = useResource(() => getEnvironments(filters), [filters]);
  return <SummaryListPage title="Environments" description="Uses the existing deployment environment identity model." loading={loading} error={error} empty="No environment data is available yet." table={data?.environments.map((env: EnvironmentSummary) => [<button className="link-button" onClick={() => { onFilter({ ...filters, environment: env.environment }); onNavigate("agents"); }}>{env.environment}</button>, env.agent_count])} columns={["Environment", "Agents"]} />;
}

function CapabilitiesPage({ filters, onNavigate }: { filters: GlobalFilters; onNavigate: (page: Page) => void }) {
  const { data, loading, error } = useResource(() => getCapabilities(filters), [filters]);
  return <SummaryListPage title="Capabilities" description="Capability deployment is informational. Remote capability changes are intentionally out of scope." loading={loading} error={error} empty="No capability data is available yet." table={data?.capabilities.map((capability: CapabilitySummary) => [<button className="link-button" onClick={() => onNavigate("agents")}>{capability.capability}</button>, capability.agents])} columns={["Capability", "Agents"]} />;
}

function IntegrationsPage({ filters }: { filters: GlobalFilters }) {
  const { data, loading, error } = useResource(() => getIntegrations(filters), [filters]);
  return (
    <section className="page">
      <PageHeader title="Integrations" description="Grafana owns telemetry exploration; this console manages the platform and links out where appropriate." />
      {loading && <LoadingState title="Loading integrations" />}
      {error && <ErrorState title="Integrations unavailable" detail={error.message} />}
      {data && <DataTable columns={["Integration", "Role", "Status", "Reference", "Actions"]} rows={data.integrations.map((integration: Integration) => [integration.name, integration.role, integration.status, integration.reference ?? integration.url ?? "Configured", <ActionLinks links={(integration.actions ?? []).map((action) => [action.label, action.url])} />])} />}
    </section>
  );
}

function SummaryListPage({ title, description, loading, error, empty, table, columns }: { title: string; description: string; loading: boolean; error: Error | null; empty: string; table?: React.ReactNode[][]; columns: string[] }) {
  return (
    <section className="page">
      <PageHeader title={title} description={description} />
      {loading && <LoadingState title={`Loading ${title.toLowerCase()}`} />}
      {error && <ErrorState title={`${title} unavailable`} detail={error.message} />}
      {!loading && !error && (!table || table.length === 0) && <EmptyState title={`No ${title.toLowerCase()}`} text={empty} />}
      {table && table.length > 0 && <DataTable columns={columns} rows={table} />}
    </section>
  );
}

function PlaceholderPage({ title, text }: { title: string; text: string }) {
  return <section className="page"><PageHeader title={title} description={text} /><div className="placeholder-card"><h3>{title}</h3><p>{text}</p></div></section>;
}

function CapabilityPicker({ selected, onChange }: { selected: string[]; onChange: (values: string[]) => void }) {
  return (
    <fieldset className="capability-picker">
      <legend>Capabilities</legend>
      {CAPABILITY_OPTIONS.map((capability) => (
        <label key={capability} className="checkbox-row">
          <input type="checkbox" checked={selected.includes(capability)} onChange={(event) => onChange(event.target.checked ? [...selected, capability] : selected.filter((item) => item !== capability))} />
          {capability}
        </label>
      ))}
    </fieldset>
  );
}

function CommandBlock({ label, value }: { label: string; value: string }) {
  return <div className="command-block"><span>{label}</span><code>{value}</code></div>;
}

function Distribution({ data, empty }: { data: Record<string, number>; empty: string }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return <Unavailable text={empty} />;
  return <MetricRows rows={entries.map(([label, value]) => [label, value])} />;
}

function ActionLinks({ links }: { links: [string, string | undefined][] }) {
  const active = links.filter(([, url]) => Boolean(url));
  if (active.length === 0) return <Unavailable text="No actions available." />;
  return <div className="action-links">{active.map(([label, url]) => <a key={label} href={url} target="_blank" rel="noreferrer">{label}</a>)}</div>;
}

function useResource<T>(loader: () => Promise<T>, deps: React.DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loader()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, deps);

  return { data, loading, error };
}

function PageHeader({ title, description }: { title: string; description: string }) {
  return <div className="page-header"><div><p className="eyebrow">Management Console</p><h2>{title}</h2><p>{description}</p></div></div>;
}

function MetricCard({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "good" | "warn" | "bad" }) {
  return <div className={`metric-card ${tone ?? ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function SummaryPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="panel"><h3>{title}</h3>{children}</div>;
}

function DataTable({ columns, rows }: { columns: string[]; rows: React.ReactNode[][] }) {
  return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>;
}

function MetricRows({ rows }: { rows: [string, React.ReactNode][] }) {
  return <dl className="metric-rows">{rows.map(([label, value]) => <React.Fragment key={label}><dt>{label}</dt><dd>{value}</dd></React.Fragment>)}</dl>;
}

function StatusBadge({ status, label }: { status: AgentStatus; label?: string }) {
  return <span className={`status ${status}`}>{label ?? status}</span>;
}

function FilterBar({ children }: { children: React.ReactNode }) {
  return <div className="filter-bar">{children}</div>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option value={option} key={option}>{option || "All"}</option>)}</select></label>;
}

function TextFilter({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return <label>{label}<input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
}

function SectionTitle({ title }: { title: string }) {
  return <h4 className="section-title">{title}</h4>;
}

function LoadingState({ title, compact }: { title: string; compact?: boolean }) {
  return <div className={compact ? "state compact" : "state"}>{title}...</div>;
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="state"><strong>{title}</strong><p>{text}</p></div>;
}

function ErrorState({ title, detail, compact }: { title: string; detail: string; compact?: boolean }) {
  return <div className={compact ? "state compact error" : "state error"}><strong>{title}</strong><p>{detail}</p></div>;
}

function Unavailable({ text }: { text: string }) {
  return <p className="unavailable">{text}</p>;
}

function formatPercent(value?: number | null) {
  return value == null ? "Available in Grafana" : `${value.toFixed(1)}%`;
}

function formatBytes(value?: number | null) {
  if (value == null) return "Available in Grafana";
  if (value > 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MiB/s`;
  if (value > 1024) return `${(value / 1024).toFixed(1)} KiB/s`;
  return `${value.toFixed(1)} B/s`;
}

function formatTime(value?: number | null) {
  return value ? new Date(value * 1000).toLocaleString() : "Never";
}

function shorten(value?: string | null) {
  return value ? `${value.slice(0, 12)}...${value.slice(-8)}` : "Unknown";
}

createRoot(document.getElementById("root")!).render(<App />);
