import { useState } from 'react';
import { BarChart3, ChevronDown, ChevronUp, Zap, Info, Wrench } from 'lucide-react';
import toolCatalog from '../../shared/tool_catalog.json';

const TOOL_METADATA_BY_ID = Object.fromEntries(
  toolCatalog.tools.map(tool => [
    tool.mcpTool,
    { name: tool.name },
  ]),
);

const TOOL_METADATA_OVERRIDES = {
  report_intent: {
    name: 'Intentvurdering',
  },
  powershell: {
    name: 'PowerShell',
  },
  'search-get_search_result_chunk': {
    name: 'Treffdetaljer',
  },
};

export function TurnSources({ toolCalls, dedupe = true, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (!toolCalls || toolCalls.length === 0) return null;

  const items = dedupe
    ? Array.from(toolCalls.reduce((merged, toolCall) => {
      const key = `${toolCall.server_name}:${toolCall.tool_name}`;
      const existing = merged.get(key);
      if (existing) {
        existing.document_names = mergeUniqueStrings(
          existing.document_names || [],
          toolCall.document_names || [],
        );
        existing.summary = mergeToolSummaries(existing.summary, toolCall.summary);
        return merged;
      }

      merged.set(key, {
        ...toolCall,
        document_names: [...(toolCall.document_names || [])],
      });
      return merged;
    }, new Map()).values())
    : toolCalls;

  const visibleItems = items.filter(toolCall =>
    toolCall?.tool_name ||
    toolCall?.server_name ||
    toolCall?.summary ||
    toolCall?.document_names?.length
  );

  if (visibleItems.length === 0) return null;

  const previewCount = visibleItems.length <= 4 ? visibleItems.length : 3;
  const hiddenCount = visibleItems.length - previewCount;

  const label = dedupe
    ? `${visibleItems.length} ${visibleItems.length === 1 ? 'source' : 'sources'} used`
    : `${visibleItems.length} ${visibleItems.length === 1 ? 'tool call' : 'tool calls'}`;

  return (
    <div className="turn-sources" onClick={() => setExpanded(e => !e)}>
      <div className="turn-sources__summary">
        <Wrench size={12} className="turn-sources__icon" />
        <span className="turn-sources__label">{label}</span>
        {!expanded && (
          <span className="turn-sources__preview">
            {visibleItems.slice(0, previewCount).map(formatToolCallLabel).join(', ')}
            {hiddenCount > 0 && ` +${hiddenCount}`}
          </span>
        )}
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </div>

      {expanded && (
        <div className="turn-sources__details">
          {visibleItems.map((toolCall, index) => {
            const labelText = formatToolCallLabel(toolCall);
            const documentNames = formatDocumentNames(toolCall.document_names || []);
            const summary = formatToolCallSummary(toolCall, documentNames);
            const itemKey = `${toolCall?.server_name || ''}:${toolCall?.tool_name || ''}:${index}`;

            return (
              <div key={itemKey} className="turn-sources__item">
                <span className="turn-sources__toolline">
                  <span className="turn-sources__tool">{labelText}</span>
                  {summary && (
                    <span className="turn-sources__intent">{summary}</span>
                  )}
                </span>
                {documentNames.length > 0 && (
                  <span className="turn-sources__documents">
                    Dokumenter: {documentNames.join(', ')}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function mergeUniqueStrings(existing = [], incoming = []) {
  const merged = [];
  const seen = new Set();

  for (const value of [...existing, ...incoming]) {
    const normalized = (value || '').trim();
    if (!normalized) continue;
    const key = normalized.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(normalized);
  }

  return merged;
}

function mergeToolSummaries(existing = '', incoming = '') {
  const current = (existing || '').trim();
  const candidate = (incoming || '').trim();
  if (!candidate) return current;
  if (!current || candidate.length > current.length) return candidate;
  return current;
}

function formatToolCallLabel(toolCall) {
  return findToolMetadata(toolCall)?.name || toolCall?.tool_name || toolCall?.server_name || 'Tool call';
}

function formatToolCallSummary(toolCall, documentNames = []) {
  const labelText = formatToolCallLabel(toolCall);
  const summary = humanizeRuntimeSummary(toolCall?.summary, labelText, toolCall?.tool_name);
  if (summary) return summary;
  return buildFallbackToolSummary(toolCall, labelText, documentNames);
}

function humanizeToolName(toolName) {
  const normalized = (toolName || '').trim();
  if (!normalized) return '';
  return normalized.replaceAll(/[_-]+/g, ' ');
}

function humanizeRuntimeSummary(summary, labelText, rawToolName) {
  const normalized = (summary || '').trim();
  if (!normalized) return '';

  const toolVariants = mergeUniqueStrings([], [
    normalized,
    labelText,
    humanizeToolName(rawToolName),
    rawToolName,
  ]).map(value => value.toLowerCase());

  if (toolVariants.length > 1 && toolVariants.slice(1).includes(normalized.toLowerCase())) {
    return '';
  }

  let text = normalized
    .replace(/([A-Za-z])[_-]+([A-Za-z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();

  const prefixReplacements = [
    [/^using\b/i, 'Brukte'],
    [/^used\b/i, 'Brukte'],
    [/^searching\b/i, 'Sokte'],
    [/^searched\b/i, 'Sokte'],
    [/^fetching\b/i, 'Hentet'],
    [/^fetched\b/i, 'Hentet'],
    [/^getting\b/i, 'Hentet'],
    [/^retrieving\b/i, 'Hentet'],
    [/^retrieved\b/i, 'Hentet'],
    [/^loading\b/i, 'Lastet'],
    [/^loaded\b/i, 'Lastet'],
    [/^reading\b/i, 'Leste'],
    [/^checking\b/i, 'Sjekket'],
    [/^checked\b/i, 'Sjekket'],
    [/^calling\b/i, 'Kjorte'],
    [/^called\b/i, 'Kjorte'],
    [/^executing\b/i, 'Kjorte'],
    [/^executed\b/i, 'Kjorte'],
    [/^running\b/i, 'Kjorte'],
    [/^ran\b/i, 'Kjorte'],
    [/^looking up\b/i, 'Slo opp'],
    [/^analyzing\b/i, 'Analyserte'],
    [/^analysing\b/i, 'Analyserte'],
  ];

  prefixReplacements.forEach(([pattern, replacement]) => {
    text = text.replace(pattern, replacement);
  });

  text = text
    .replace(/\bdocuments\b/gi, 'dokumenter')
    .replace(/\bdocument\b/gi, 'dokument')
    .replace(/\bsources\b/gi, 'kilder')
    .replace(/\bsource\b/gi, 'kilde')
    .replace(/\bresults\b/gi, 'treff')
    .replace(/\bresult\b/gi, 'treff')
    .replace(/\bquery\b/gi, 'sporring')
    .replace(/\bqueries\b/gi, 'sporringer')
    .replace(/\btool\b/gi, 'verktoy')
    .replace(/\btools\b/gi, 'verktoy');

  return ensureSentence(capitalizeText(text));
}

function buildFallbackToolSummary(toolCall, labelText, documentNames = []) {
  const toolId = normalizeToolId(toolCall);
  const serverName = humanizeServerName(toolCall?.server_name);

  if (toolId.includes('fetch document')) {
    if (documentNames[0]) {
      return `Hentet innhold fra ${documentNames[0]}.`;
    }
    return 'Hentet innhold fra et dokument.';
  }

  if (toolId.includes('list documents')) {
    return 'Sjekket hvilke dokumenter som var tilgjengelige.';
  }

  if (toolId.includes('get search result chunk')) {
    if (documentNames[0]) {
      return `Hentet flere detaljer fra ${documentNames[0]}.`;
    }
    return 'Hentet flere detaljer fra et soketreff.';
  }

  if (toolId.includes('search')) {
    if (documentNames.length === 1) {
      return `Sokte i ${documentNames[0]} etter relevant innhold.`;
    }
    if (documentNames.length > 1) {
      return `Sokte i ${documentNames.length} dokumenter etter relevant innhold.`;
    }
    return `Sokte etter relevant innhold med ${labelText.toLowerCase()}.`;
  }

  if (toolId.includes('forward geocode')) {
    return 'Slo opp et stedsnavn for a finne koordinater.';
  }

  if (toolId.includes('reverse geocode')) {
    return 'Slo opp sted og adresse fra koordinater.';
  }

  if (toolId.includes('get drawn layers')) {
    return 'Leste lagene som allerede ligger pa kartet.';
  }

  if (toolId.includes('draw shape')) {
    return 'Tegnet resultatet direkte pa kartet.';
  }

  if (toolId.includes('buffer')) {
    return 'Lagde en buffersone rundt det valgte omradet.';
  }

  if (toolId.includes('intersection')) {
    return 'Fant overlappen mellom geometrier.';
  }

  if (documentNames.length === 1) {
    return `${labelText} brukte ${documentNames[0]} som kilde.`;
  }

  if (documentNames.length > 1) {
    return `${labelText} brukte ${documentNames.length} dokumenter som kilder.`;
  }

  if (labelText && serverName) {
    return `${labelText} ble brukt via ${serverName}.`;
  }

  if (labelText) {
    return `${labelText} ble brukt for a lage svaret.`;
  }

  if (serverName) {
    return `Et verktoy ble brukt via ${serverName}.`;
  }

  return '';
}

function normalizeToolId(toolCall) {
  return [toolCall?.server_name, toolCall?.tool_name, toolCall?.mcp_tool_name]
    .filter(Boolean)
    .join(' ')
    .replaceAll(/[_-]+/g, ' ')
    .toLowerCase();
}

function humanizeServerName(serverName) {
  const normalized = (serverName || '').trim();
  if (!normalized) return '';
  return normalized.replaceAll(/[_-]+/g, ' ');
}

function capitalizeText(text) {
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function ensureSentence(text) {
  const normalized = (text || '').trim();
  if (!normalized) return '';
  if (/[.!?]$/.test(normalized)) return normalized;
  return `${normalized}.`;
}

function formatDocumentNames(documentNames = []) {
  return mergeUniqueStrings(
    [],
    documentNames.map(documentName => {
      const normalized = (documentName || '').trim().replaceAll('\\', '/');
      return normalized.includes('/') ? normalized.split('/').pop() : normalized;
    }),
  );
}

function findToolMetadata(toolCall) {
  for (const candidate of getToolIdCandidates(toolCall)) {
    if (TOOL_METADATA_OVERRIDES[candidate]) {
      return TOOL_METADATA_OVERRIDES[candidate];
    }
    if (TOOL_METADATA_BY_ID[candidate]) {
      return TOOL_METADATA_BY_ID[candidate];
    }
  }

  return null;
}

function getToolIdCandidates(toolCall) {
  const candidates = [];
  const rawServerName = (toolCall?.server_name || '').trim();
  const serverName = normalizeServerAlias(rawServerName);

  for (const value of [toolCall?.tool_name, toolCall?.mcp_tool_name]) {
    const normalized = (value || '').trim();
    if (!normalized) continue;
    candidates.push(normalized);
    if (serverName && !normalized.startsWith(`${serverName}-`)) {
      candidates.push(`${serverName}-${normalized}`);
    }
    if (rawServerName && rawServerName !== serverName && !normalized.startsWith(`${rawServerName}-`)) {
      candidates.push(`${rawServerName}-${normalized}`);
    }
  }

  if (serverName) {
    candidates.push(serverName);
  }

  if (rawServerName && rawServerName !== serverName) {
    candidates.push(rawServerName);
  }

  return mergeUniqueStrings([], candidates);
}

function normalizeServerAlias(serverName) {
  const normalized = (serverName || '').trim();
  const aliases = {
    blob_docs: 'docs',
    docs_server: 'docs',
    search_server: 'search',
    geo_server: 'geo',
    vector_server: 'vector',
    map_server: 'map',
  };
  return aliases[normalized] || normalized;
}

/**
 * Compact per-turn usage summary rendered below an assistant message.
 *
 * Shows model, premium requests consumed, and token counts for the turn.
 * Collapsed by default — click to expand full details.
 */
export function TurnUsage({ usage }) {
  const [expanded, setExpanded] = useState(false);

  if (!usage) return null;

  const { model, premium_requests, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, model_multiplier } = usage;

  // Don't render if there's truly nothing to show.
  const hasTokens = (input_tokens || 0) + (output_tokens || 0) > 0;
  const hasCost = (premium_requests || 0) > 0;
  if (!hasTokens && !hasCost) return null;

  return (
    <div className="turn-usage" onClick={() => setExpanded(e => !e)}>
      <div className="turn-usage__summary">
        <Zap size={12} className="turn-usage__icon" />
        {hasCost && (
          <span className="turn-usage__cost">
            {formatNumber(premium_requests)} calls
          </span>
        )}
        {hasTokens && (
          <span className="turn-usage__tokens">
            {formatNumber(input_tokens + output_tokens)} tokens
          </span>
        )}
        {model && (
          <span className="turn-usage__model">{model}</span>
        )}
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </div>

      {expanded && (
        <div className="turn-usage__details">
          <div className="turn-usage__row">
            <span>Input tokens</span>
            <span>{formatNumber(input_tokens)}</span>
          </div>
          <div className="turn-usage__row">
            <span>Output tokens</span>
            <span>{formatNumber(output_tokens)}</span>
          </div>
          {(cache_read_tokens > 0 || cache_write_tokens > 0) && (
            <>
              <div className="turn-usage__row">
                <span>Cache read</span>
                <span>{formatNumber(cache_read_tokens)}</span>
              </div>
              <div className="turn-usage__row">
                <span>Cache write</span>
                <span>{formatNumber(cache_write_tokens)}</span>
              </div>
            </>
          )}
          {model_multiplier != null && (
            <div className="turn-usage__row">
              <span>Model multiplier</span>
              <span>×{model_multiplier}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


/**
 * Session-level aggregate footer showing cumulative totals across all turns.
 */
export function SessionUsageFooter({ session }) {
  if (!session) return null;

  const {
    total_premium_requests,
    total_input_tokens,
    total_output_tokens,
    current_context_tokens,
    context_token_limit,
  } = session;

  const hasTotals = (total_premium_requests || 0) + (total_input_tokens || 0) + (total_output_tokens || 0) > 0;
  if (!hasTotals) return null;

  return (
    <div className="session-usage-footer">
      <BarChart3 size={12} className="session-usage-footer__icon" />
      <span>Session: {formatNumber(total_premium_requests)} calls</span>
      <span className="session-usage-footer__sep">·</span>
      <span>{formatNumber(total_input_tokens + total_output_tokens)} tokens</span>
      {current_context_tokens != null && context_token_limit != null && (
        <>
          <span className="session-usage-footer__sep">·</span>
          <span>Context: {formatNumber(current_context_tokens)}/{formatNumber(context_token_limit)}</span>
        </>
      )}
    </div>
  );
}


/**
 * Monthly premium usage bar with percent/requests toggle.
 *
 * Driven entirely by dynamic data from the backend – never hard-codes
 * plan allowances or model multipliers.
 */
export function MonthlyUsageBar({ monthly }) {
  const [mode, setMode] = useState('percent'); // 'percent' | 'requests'

  if (!monthly) return null;

  const {
    confidence,
    used_requests,
    entitlement_requests,
    is_unlimited,
    remaining_percentage,
    overage,
    reset_date,
  } = monthly;

  // If data is entirely unavailable, show nothing or a minimal indicator.
  if (confidence === 'unavailable') {
    return null;
  }

  const hasRequests = used_requests != null && entitlement_requests != null;

  let percentUsed = null;
  if (remaining_percentage != null) {
    // remaining_percentage is 0.0–1.0; invert to get "used".
    percentUsed = Math.round((1 - remaining_percentage) * 100);
  } else if (hasRequests && entitlement_requests > 0) {
    percentUsed = Math.round((used_requests / entitlement_requests) * 100);
  }

  const barWidth = is_unlimited
    ? 0
    : Math.min(percentUsed ?? 0, 100);

  const isOverage = (overage || 0) > 0;

  const toggleMode = () => setMode(m => m === 'percent' ? 'requests' : 'percent');

  return (
    <div className="monthly-usage-bar">
      <div className="monthly-usage-bar__header">
        <span className="monthly-usage-bar__label">
          Premium requests
          {confidence === 'estimated' && (
            <span className="monthly-usage-bar__badge" title="Estimated — authoritative data not yet available">
              <Info size={10} /> est.
            </span>
          )}
        </span>
        <button
          className="monthly-usage-bar__toggle"
          onClick={toggleMode}
          title="Toggle between percent and request count"
        >
          {is_unlimited ? (
            '∞ Unlimited'
          ) : mode === 'percent' ? (
            percentUsed != null ? `${percentUsed}%` : '—'
          ) : (
            hasRequests ? `${formatNumber(used_requests)} / ${formatNumber(entitlement_requests)}` : '—'
          )}
        </button>
      </div>

      {!is_unlimited && (
        <div className="monthly-usage-bar__track">
          <div
            className={`monthly-usage-bar__fill${isOverage ? ' monthly-usage-bar__fill--overage' : ''}`}
            style={{ width: `${barWidth}%` }}
          />
        </div>
      )}

      {reset_date && (
        <div className="monthly-usage-bar__reset">
          Resets {formatResetDate(reset_date)}
        </div>
      )}
    </div>
  );
}


/**
 * Unified usage strip rendered directly above the message input.
 *
 * Left side  — session aggregate: calls + tokens for the current chat.
 * Right side — monthly premium request quota (clickable to toggle % vs REQ).
 * A thin progress bar spans the full width behind both sections.
 *
 * When monthly data is unavailable the right side shows a greyed placeholder
 * so the user knows the feature is present but data hasn't arrived yet.
 */
export function InputAreaUsageBar({ monthly, session }) {
  const [mode, setMode] = useState('percent'); // 'percent' | 'requests'

  // — Monthly data ——————————————————————————————————————————————————————————
  const confidence = monthly?.confidence ?? 'unavailable';
  const unavailable = confidence === 'unavailable';

  const {
    used_requests = null,
    entitlement_requests = null,
    is_unlimited = false,
    remaining_percentage = null,
    overage = null,
    reset_date = null,
  } = monthly ?? {};

  let percentUsed = null;
  if (!unavailable) {
    if (remaining_percentage != null) {
      percentUsed = Math.round((1 - remaining_percentage) * 100);
    } else if (used_requests != null && entitlement_requests != null && entitlement_requests > 0) {
      percentUsed = Math.round((used_requests / entitlement_requests) * 100);
    }
  }

  const barWidth = unavailable || is_unlimited ? 0 : Math.min(percentUsed ?? 0, 100);
  const isOverage = (overage || 0) > 0;

  // — Session data ——————————————————————————————————————————————————————————
  const sessionCalls = session?.total_premium_requests ?? null;
  const sessionTokens = session
    ? (session.total_input_tokens || 0) + (session.total_output_tokens || 0)
    : null;
  const hasSession = (sessionCalls != null && sessionCalls > 0) ||
                     (sessionTokens != null && sessionTokens > 0);

  function sessionLabel() {
    const parts = [];
    if (sessionCalls != null && sessionCalls > 0) parts.push(`${formatNumber(sessionCalls)} calls`);
    if (sessionTokens != null && sessionTokens > 0) parts.push(`${formatNumber(sessionTokens)} tokens`);
    return parts.join(' · ');
  }

  function monthlyLabel() {
    if (unavailable) return 'Usage unavailable';
    if (mode === 'percent') {
      if (is_unlimited) return '∞ Unlimited';
      return percentUsed != null ? `${percentUsed}% used` : '—';
    }
    // requests mode
    if (is_unlimited) return '∞ / ∞ REQ';
    if (used_requests != null && entitlement_requests != null) {
      return `${formatNumber(used_requests)} / ${formatNumber(entitlement_requests)} REQ`;
    }
    return '—';
  }

  // Gray the whole bar only when there is truly nothing to show.
  const fullyUnavailable = !hasSession && unavailable;

  return (
    <div className={`input-usage-bar${fullyUnavailable ? ' input-usage-bar--unavailable' : ''}${isOverage ? ' input-usage-bar--overage' : ''}`}>
      <div className="input-usage-bar__track">
        <div
          className="input-usage-bar__fill"
          style={{ width: `${barWidth}%` }}
        />
      </div>
      <div className="input-usage-bar__row">
        {/* Left: session aggregate */}
        {hasSession && (
          <span className="input-usage-bar__session">
            <BarChart3 size={10} />
            {sessionLabel()}
          </span>
        )}

        {/* Right: monthly quota toggle + reset date */}
        <span className="input-usage-bar__right">
          <button
            className={`input-usage-bar__monthly${unavailable ? ' input-usage-bar__monthly--unavailable' : ''}`}
            onClick={unavailable ? undefined : () => setMode(m => m === 'percent' ? 'requests' : 'percent')}
            disabled={unavailable}
            title={unavailable ? 'Premium request usage data not yet available' : 'Click to toggle view'}
          >
            {monthlyLabel()}
            {confidence === 'estimated' && !unavailable && (
              <span className="input-usage-bar__est" title="Estimated — authoritative data not yet available">
                <Info size={9} /> est.
              </span>
            )}
          </button>
          {reset_date && !unavailable && (
            <span className="input-usage-bar__reset">resets {formatResetDate(reset_date)}</span>
          )}
        </span>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatNumber(n) {
  if (n == null) return '0';
  const num = Number(n);
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return String(Math.round(num));
}

function formatResetDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}
