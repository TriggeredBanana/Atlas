import { useCallback, useEffect, useState } from 'react';
import { ChevronRight, ChevronDown, MessageSquare, Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiFetch } from '../utils/auth';
import { ConfirmDialog } from './ConfirmDialog';
import { TurnSources } from './UsageDisplay';

/**
 * ChatHistory
 *
 * Renders the list of past chats with:
 *   - Per-item checkboxes for selection
 *   - "Select all" header row
 *   - Bulk delete button (shown when ≥1 item selected)
 *   - Confirmation dialog before deletion
 *   - Expand/collapse to preview messages
 *   - "Fortsett" button to resume a chat
 *
 * Props:
 *   chats         — Array<{ id, title, created_at, updated_at }>
 *   activeChatId  — currently active chat id (highlighted)
 *   onContinue(chatId)       — called when "Fortsett" is clicked
 *   onDeleteMany([chatIds])  — called to delete one or more chats
 *   isLoaded      — whether the chat list has finished loading for the current user
 *   loadError     — error text when the chat list fails to load
 *   onRetryLoad() — retry callback for chat-list loading
 */
export function ChatHistory({ chats, activeChatId, onContinue, onDeleteMany, isLoaded, loadError = '', onRetryLoad }) {
  const [expanded, setExpanded] = useState(new Set());
  const [messageCache, setMessageCache] = useState({});
  const [messageLoadErrors, setMessageLoadErrors] = useState({});
  const [loading, setLoading] = useState(new Set());
  const [selected, setSelected] = useState(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const allSelected = chats.length > 0 && selected.size === chats.length;
  const someSelected = selected.size > 0 && !allSelected;

  const loadMessages = useCallback(async chatId => {
    setLoading(prev => {
      if (prev.has(chatId)) return prev;
      return new Set([...prev, chatId]);
    });
    setMessageLoadErrors(prev => {
      if (!(chatId in prev)) return prev;
      const next = { ...prev };
      delete next[chatId];
      return next;
    });

    try {
      const res = await apiFetch(`/api/chats/${chatId}/messages`);
      if (!res.ok) {
        setMessageLoadErrors(prev => ({ ...prev, [chatId]: 'Kunne ikke laste meldingene.' }));
        return;
      }
      const data = await res.json();
      setMessageCache(prev => ({ ...prev, [chatId]: data.messages || [] }));
    } catch {
      setMessageLoadErrors(prev => ({ ...prev, [chatId]: 'Kunne ikke laste meldingene.' }));
    } finally {
      setLoading(prev => {
        const next = new Set(prev);
        next.delete(chatId);
        return next;
      });
    }
  }, []);

  useEffect(() => {
    if (!isLoaded) {
      return;
    }

    const validChatIds = new Set(chats.map(chat => chat.id));

    setExpanded(prev => {
      const next = new Set(Array.from(prev).filter(chatId => validChatIds.has(chatId)));
      return next.size === prev.size ? prev : next;
    });

    setSelected(prev => {
      const next = new Set(Array.from(prev).filter(chatId => validChatIds.has(chatId)));
      return next.size === prev.size ? prev : next;
    });

    setMessageCache(prev => {
      const nextEntries = Object.entries(prev).filter(([chatId]) => validChatIds.has(chatId));
      return nextEntries.length === Object.keys(prev).length
        ? prev
        : Object.fromEntries(nextEntries);
    });

    setMessageLoadErrors(prev => {
      const nextEntries = Object.entries(prev).filter(([chatId]) => validChatIds.has(chatId));
      return nextEntries.length === Object.keys(prev).length
        ? prev
        : Object.fromEntries(nextEntries);
    });
  }, [chats, isLoaded]);

  useEffect(() => {
    chats.forEach(chat => {
      if (!expanded.has(chat.id) || messageCache[chat.id] || loading.has(chat.id) || messageLoadErrors[chat.id]) {
        return;
      }
      void loadMessages(chat.id);
    });
  }, [chats, expanded, loading, messageCache, messageLoadErrors, loadMessages]);

  // Expand / collapse

  async function handleToggle(chatId) {
    if (expanded.has(chatId)) {
      setExpanded(prev => { const next = new Set(prev); next.delete(chatId); return next; });
      return;
    }
    if (!messageCache[chatId] && !loading.has(chatId)) {
      await loadMessages(chatId);
    }
    setExpanded(prev => new Set([...prev, chatId]));
  }

  // Selection

  function toggleSelectAll() {
    setSelected(selected.size === chats.length ? new Set() : new Set(chats.map(c => c.id)));
  }

  function toggleSelectOne(chatId) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(chatId) ? next.delete(chatId) : next.add(chatId);
      return next;
    });
  }

  // Deletion

  function handleDeleteConfirmed() {
    setShowDeleteConfirm(false);
    onDeleteMany(Array.from(selected));
    setSelected(new Set());
  }

  // Empty state

  if (!isLoaded) {
    return (
      <div className="chat-history">
        <p className="chat-history-empty">Laster tidligere samtaler…</p>
      </div>
    );
  }

  if (loadError && chats.length === 0) {
    return (
      <div className="chat-history">
        <p className="chat-history-empty">{loadError}</p>
        {onRetryLoad && (
          <button className="chat-history-retry" type="button" onClick={() => void onRetryLoad()}>
            Prøv igjen
          </button>
        )}
      </div>
    );
  }

  if (chats.length === 0) {
    return (
      <div className="chat-history">
        <p className="chat-history-empty">Ingen tidligere samtaler.</p>
      </div>
    );
  }

  const deleteCount = selected.size;
  const deleteMessage = deleteCount === 1
    ? 'Er du sikker på at du vil slette denne samtalen? Handlingen kan ikke angres.'
    : `Er du sikker på at du vil slette ${deleteCount} samtaler? Handlingen kan ikke angres.`;

  return (
    <div className="chat-history">
      {loadError && (
        <div className="history-load-error">
          <p className="history-loading">{loadError}</p>
          {onRetryLoad && (
            <button className="chat-history-retry" type="button" onClick={() => void onRetryLoad()}>
              Prøv igjen
            </button>
          )}
        </div>
      )}

      {/* Select-all / bulk-action header row */}
      <div className="history-select-bar">
        <label className="history-select-all-label">
          <input
            type="checkbox"
            className="history-checkbox"
            checked={allSelected}
            ref={el => { if (el) el.indeterminate = someSelected; }}
            onChange={toggleSelectAll}
          />
          <span className="history-select-all-text">Velg alle</span>
        </label>

        {selected.size > 0 && (
          <button
            className="history-bulk-delete-btn"
            title={`Slett ${deleteCount} valgte samtale${deleteCount > 1 ? 'r' : ''}`}
            onClick={() => setShowDeleteConfirm(true)}
          >
            <Trash2 size={14} />
            Slett ({deleteCount})
          </button>
        )}
      </div>

      {/* Chat items */}
      {chats.map(chat => {
        const isExpanded = expanded.has(chat.id);
        const isActive = chat.id === activeChatId;
        const isLoading = loading.has(chat.id);
        const messageLoadError = messageLoadErrors[chat.id] || '';
        const isSelected = selected.has(chat.id);
        const messages = messageCache[chat.id] || [];

        return (
          <div
            key={chat.id}
            className={`history-item${isActive ? ' history-item--active' : ''}${isExpanded ? ' history-item--expanded' : ''}${isSelected ? ' history-item--selected' : ''}`}
          >
            {/* Header row */}
            <div
              className="history-item-header"
              onClick={() => handleToggle(chat.id)}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && handleToggle(chat.id)}
              aria-expanded={isExpanded}
            >
              {/* Checkbox — stop propagation so it doesn't toggle expand */}
              <span onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
                <input
                  type="checkbox"
                  className="history-checkbox"
                  checked={isSelected}
                  onChange={() => toggleSelectOne(chat.id)}
                  aria-label={`Velg "${chat.title || 'Ny samtale'}"`}
                />
              </span>

              <MessageSquare size={14} className="history-item-icon" />
              <span className="history-item-title" title={chat.title}>
                {chat.title || 'Ny samtale'}
              </span>

              <div className="history-item-actions" onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
                <button
                  className="history-item-btn--fortsett"
                  title="Fortsett denne samtalen"
                  type="button"
                  onClick={() => onContinue(chat.id)}
                  onKeyDown={e => e.stopPropagation()}
                >
                  Fortsett
                </button>
              </div>

              <span className="history-item-chevron">
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
            </div>

            {/* Expanded message preview */}
            {isExpanded && (
              <div className="history-messages">
                {isLoading ? (
                  <p className="history-loading">Laster meldinger…</p>
                ) : messageLoadError ? (
                  <div className="history-load-error">
                    <p className="history-loading">{messageLoadError}</p>
                    <button className="history-retry-btn" type="button" onClick={() => void loadMessages(chat.id)}>
                      Prøv igjen
                    </button>
                  </div>
                ) : messages.length === 0 ? (
                  <p className="history-loading">Ingen meldinger.</p>
                ) : (
                  messages.map(msg => {
                    const toolCalls = msg.metadata?.turn_usage?.tool_calls || [];

                    return (
                      <div key={msg.id} className={`history-msg-stack history-msg-stack--${msg.role}`}>
                        <div className={`history-msg history-msg--${msg.role}`}>
                          {msg.role === 'assistant' ? (
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {(msg.content || '').slice(0, 300) + ((msg.content || '').length > 300 ? '…' : '')}
                            </ReactMarkdown>
                          ) : (
                            <span>
                              {(msg.content || '').slice(0, 300)}
                              {(msg.content || '').length > 300 ? '…' : ''}
                            </span>
                          )}
                        </div>

                        {msg.role === 'assistant' && toolCalls.length > 0 && (
                          <div className="history-msg-sources">
                            <TurnSources toolCalls={toolCalls} dedupe={false} defaultExpanded />
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Confirmation dialog */}
      {showDeleteConfirm && (
        <ConfirmDialog
          title="Slett samtaler?"
          message={deleteMessage}
          confirmLabel={`Slett ${deleteCount === 1 ? 'samtalen' : `${deleteCount} samtaler`}`}
          cancelLabel="Avbryt"
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}
    </div>
  );
}
