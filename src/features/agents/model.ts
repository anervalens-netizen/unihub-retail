export type AgentListTab = 'active' | 'movement' | 'inactive' | 'churned' | 'all';
export type AgentsMainTab = 'overview' | 'grile' | 'analysis';

const AGENT_LIST_TABS = new Set<AgentListTab>(['active', 'movement', 'inactive', 'churned', 'all']);
const AGENTS_MAIN_TABS = new Set<AgentsMainTab>(['overview', 'grile', 'analysis']);

export function deserializeAgentListTab(raw: string, fallback: AgentListTab): AgentListTab { return AGENT_LIST_TABS.has(raw as AgentListTab) ? (raw as AgentListTab) : fallback; }
export function deserializeAgentsMainTab(raw: string, fallback: AgentsMainTab): AgentsMainTab { return AGENTS_MAIN_TABS.has(raw as AgentsMainTab) ? (raw as AgentsMainTab) : fallback; }
export function deserializeSelectedAgent(raw: string): string | null { return raw || null; }
export function hasNoSelectedAgent(value: string | null): boolean { return value === null; }
