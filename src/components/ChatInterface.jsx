import { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react';
import { ArrowUp, Paperclip, FileText, X, Plus, Wrench, ChevronDown, ChevronRight, Brain } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { AuthModal } from './AuthModal';
import { ChatHistory } from './ChatHistory';
import { TurnUsage, MonthlyUsageBar, InputAreaUsageBar, TurnSources } from './UsageDisplay';
import toolCatalog from '../../shared/tool_catalog.json';
import {
  apiFetch,
  clearActiveChatId,
  clearToken,
  getActiveChatId,
  getToken,
  setActiveChatId,
} from '../utils/auth';

const _TOOL_BY_MCP_ID = Object.fromEntries(
  toolCatalog.tools.map(t => [t.mcpTool, t])
);

const THINKING_BOUNDARY_CHARS = '.!?;:,)]';

function isThinkingSentenceStart(char) {
  return char === '[' || /[A-ZÆØÅ]/.test(char);
}

function isThinkingWordStart(char) {
  return /[A-Za-zÆØÅæøå]/.test(char);
}

function normalizeThinkingText(text) {
  if (!text) return '';

  return text
    .replace(/(\]|\))(?=[A-Za-zÆØÅæøå])/g, '$1 ')
    .replace(/([.!?;:])(?=[A-ZÆØÅ]|\[)/g, '$1 ')
    .replace(/,(?=[A-ZÆØÅ]|\[)/g, ', ');
}

function appendThinkingChunk(existing, incoming) {
  if (!incoming) return existing || '';
  if (!existing) return normalizeThinkingText(incoming);

  const lastChar = existing[existing.length - 1];
  const firstChar = incoming[0];
  const needsSpace = (
    !/\s/.test(lastChar)
    && !/\s/.test(firstChar)
    && (
      (/[.!?;:,]/.test(lastChar) && isThinkingSentenceStart(firstChar))
      || (THINKING_BOUNDARY_CHARS.includes(lastChar) && (isThinkingWordStart(firstChar) || firstChar === '['))
    )
  );

  return normalizeThinkingText(`${existing}${needsSpace ? ' ' : ''}${incoming}`);
}

// Reveal settings for the thinking drain loop.  The renderer keeps a small
// buffer while streaming so upstream pauses do not leave the cursor stranded
// mid-word, then drains that buffer at a steady time-based pace.
const THINKING_REVEAL_CHARS_PER_SECOND = 46;
const THINKING_STREAM_BUFFER_CHARS = 48;
const THINKING_MIN_VISIBLE_CHARS = 24;
const THINKING_MAX_FRAME_CHARS = 4;

function findThinkingRevealTarget(text, currentLength, isStreaming) {
  const length = text?.length || 0;
  if (!isStreaming) return length;
  if (length <= THINKING_MIN_VISIBLE_CHARS) return 0;

  const bufferedTarget = Math.max(0, length - THINKING_STREAM_BUFFER_CHARS);
  if (bufferedTarget <= currentLength) return currentLength;

  const searchStart = Math.max(currentLength, bufferedTarget - 48);
  for (let idx = bufferedTarget; idx > searchStart; idx -= 1) {
    const char = text[idx - 1];
    if (/\s/.test(char) || THINKING_BOUNDARY_CHARS.includes(char)) return idx;
  }

  return bufferedTarget;
}

function ThinkingBlock({ thinking, isStreaming }) {
  const [expanded, setExpanded] = useState(isStreaming);
  const contentRef = useRef(null);
  const userScrolledUp = useRef(false);

  // Revealed-text cursor — decoupled from the raw prop so bursts are smoothed.
  const [displayedLength, setDisplayedLength] = useState(() => (
    isStreaming ? 0 : (thinking?.length || 0)
  ));
  const thinkingRef = useRef(thinking);
  const displayedLengthRef = useRef(0);
  const revealCarryRef = useRef(0);

  // Keep ref in sync every render so the interval closure always sees the
  // latest value without needing it in the dependency array.
  useEffect(() => {
    thinkingRef.current = thinking;
  });

  // Scroll detection.
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    function onScroll() {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 20;
      userScrolledUp.current = !atBottom;
    }
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, [expanded]);

  // Drain loop: reveal text based on elapsed time rather than chunk arrival.
  // During streaming, stop at a stable boundary behind the live buffer; once
  // streaming ends, snap to the complete sanitized trace.
  useEffect(() => {
    if (!isStreaming) {
      const full = thinkingRef.current?.length || 0;
      displayedLengthRef.current = full;
      revealCarryRef.current = 0;
      const frameId = requestAnimationFrame(() => setDisplayedLength(full));
      return () => cancelAnimationFrame(frameId);
    }

    let frameId = null;
    let previousTime = performance.now();

    function drain(now) {
      const elapsedSeconds = Math.min((now - previousTime) / 1000, 0.25);
      previousTime = now;

      const target = findThinkingRevealTarget(
        thinkingRef.current,
        displayedLengthRef.current,
        true,
      );
      const current = displayedLengthRef.current;
      if (current < target) {
        revealCarryRef.current += elapsedSeconds * THINKING_REVEAL_CHARS_PER_SECOND;
        const wholeChars = Math.floor(revealCarryRef.current);
        if (wholeChars > 0) {
          const charsToReveal = Math.min(wholeChars, THINKING_MAX_FRAME_CHARS);
          revealCarryRef.current = Math.max(0, revealCarryRef.current - charsToReveal);
          const next = Math.min(current + charsToReveal, target);
          displayedLengthRef.current = next;
          setDisplayedLength(next);
        }
      } else {
        revealCarryRef.current = 0;
      }

      frameId = requestAnimationFrame(drain);
    }

    frameId = requestAnimationFrame(drain);

    return () => {
      if (frameId !== null) cancelAnimationFrame(frameId);
    };
  }, [isStreaming]);

  // Auto-scroll as text is revealed.
  useLayoutEffect(() => {
    const el = contentRef.current;
    if (expanded && el && !userScrolledUp.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [displayedLength, expanded]);

  if (!thinking) return null;

  const effectiveDisplayedLength = isStreaming ? displayedLength : thinking.length;
  const displayText = normalizeThinkingText(thinking.slice(0, effectiveDisplayedLength));

  return (
    <div className={`thinking-block${isStreaming ? ' thinking-block--streaming' : ''}`}>
      <button className="thinking-toggle" onClick={() => setExpanded(e => !e)}>
        <Brain size={14} className="thinking-icon" />
        <span className="thinking-label">
          {isStreaming ? 'Tenker…' : 'Tankeprosess'}
        </span>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {expanded && displayText && (
        <div ref={contentRef} className={`thinking-content${isStreaming ? ' thinking-content--streaming' : ''}`}>
          {displayText}{isStreaming && <span className="thinking-cursor" aria-hidden="true">▋</span>}
        </div>
      )}
    </div>
  );
}

export function ChatInterface({ externalUser, onUserChange, drawnLayers = [], onLayerCreated, onSetDrawnLayers, selectedTools = [], onClearSelectedTools, onRemoveTool, onAiStatusChange }) {
  const CHAT_SCROLL_RESUME_THRESHOLD = 2;

  // Auth state
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  // Tab state
  const [activeTab, setActiveTab] = useState('chat');

  // Chat state
  const [activeChatId, setActiveChatIdState] = useState(null);
  const [messages, setMessages] = useState([]);
  const [chats, setChats] = useState([]);
  const [chatsLoaded, setChatsLoaded] = useState(false);
  const [chatsLoading, setChatsLoading] = useState(false);
  const [chatListError, setChatListError] = useState('');

  // Input state
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const messagesRef = useRef(null);
  const fileInputRef = useRef(null);
  const streamAbortRef = useRef(null);
  const textareaRef = useRef(null);
  const assistantIdx = useRef(null);
  const userScrolledUpRef = useRef(false);
  const userScrollInteractionRef = useRef(false);

  const MAX_TEXTAREA_HEIGHT = 250; // ~5 rows

  // Auto-resize textarea as user types
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const newHeight = Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT);
    el.style.height = `${newHeight}px`;
    el.style.overflowY = el.scrollHeight > MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden';
    el.style.borderRadius = newHeight > 44 ? '14px' : '999px';
  }, [input]);

  // Usage tracking state
  const [usageSession, setUsageSession] = useState(null);
  const [usageMonthly, setUsageMonthly] = useState(null);

  function isChatScrolledToBottom(el) {
    return el.scrollHeight - el.scrollTop - el.clientHeight <= CHAT_SCROLL_RESUME_THRESHOLD;
  }

  function resetAutoFollow() {
    userScrolledUpRef.current = false;
    userScrollInteractionRef.current = false;
  }

  // Any upward movement pauses follow mode immediately. Follow only resumes once
  // the user intentionally returns to the bottom of the message list.
  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;

    function pauseAutoFollow() {
      userScrolledUpRef.current = true;
    }

    function syncAutoFollowWithPosition() {
      if (isChatScrolledToBottom(el)) {
        if (!userScrollInteractionRef.current) {
          userScrolledUpRef.current = false;
        }
      } else {
        userScrolledUpRef.current = true;
      }
    }

    function onPointerDown() {
      userScrollInteractionRef.current = true;
    }

    function onPointerUp() {
      userScrollInteractionRef.current = false;
      syncAutoFollowWithPosition();
    }

    function onPointerCancel() {
      userScrollInteractionRef.current = false;
      syncAutoFollowWithPosition();
    }

    function onWheel(e) {
      if (e.deltaY < 0) {
        pauseAutoFollow();
      }
    }

    function onTouchStart() {
      userScrollInteractionRef.current = true;
    }

    function onTouchEnd() {
      userScrollInteractionRef.current = false;
      syncAutoFollowWithPosition();
    }

    function onKeyDown(e) {
      if (!isLoading) return;
      if (
        e.key === 'ArrowUp' ||
        e.key === 'ArrowDown' ||
        e.key === 'PageUp' ||
        e.key === 'PageDown' ||
        e.key === 'Home' ||
        e.key === 'End' ||
        e.key === ' '
      ) {
        pauseAutoFollow();
      }
    }

    function onScroll() {
      syncAutoFollowWithPosition();
    }

    syncAutoFollowWithPosition();
    el.addEventListener('pointerdown', onPointerDown, { passive: true });
    window.addEventListener('pointerup', onPointerUp, { passive: true });
    window.addEventListener('pointercancel', onPointerCancel, { passive: true });
    el.addEventListener('wheel', onWheel, { passive: true });
    el.addEventListener('touchstart', onTouchStart, { passive: true });
    window.addEventListener('touchend', onTouchEnd, { passive: true });
    window.addEventListener('touchcancel', onTouchEnd, { passive: true });
    window.addEventListener('keydown', onKeyDown);
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      el.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerCancel);
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('touchstart', onTouchStart);
      window.removeEventListener('touchend', onTouchEnd);
      window.removeEventListener('touchcancel', onTouchEnd);
      window.removeEventListener('keydown', onKeyDown);
      el.removeEventListener('scroll', onScroll);
    };
  }, [activeTab, isLoading, CHAT_SCROLL_RESUME_THRESHOLD]);

  useLayoutEffect(() => {
    if (userScrolledUpRef.current || userScrollInteractionRef.current) return;
    const el = messagesRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  // External logout signal (e.g. header logout button)
  useEffect(() => {
    if (externalUser === null && user !== null) {
      streamAbortRef.current?.abort();
      setUser(null);
      setActiveChatIdState(null);
      setMessages([]);
      setChats([]);
      setChatsLoaded(false);
      setChatsLoading(false);
      setChatListError('');
      setActiveTab('chat');
      setInput('');
      setAttachments([]);
      setUsageSession(null);
      setUsageMonthly(null);
      onSetDrawnLayers?.([]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalUser]);

  // Abort any in-flight streaming fetch when the component unmounts.
  useEffect(() => {
    return () => { streamAbortRef.current?.abort(); };
  }, []);

  // On mount: verify token, restore last active chat
  useEffect(() => {
    async function init() {
      const token = getToken();
      if (!token) {
        setAuthChecked(true);
        return;
      }
      try {
        const res = await apiFetch('/api/auth/me');
        if (!res.ok) {
          clearToken();
          clearActiveChatId();
          setAuthChecked(true);
          return;
        }
        const data = await res.json();
        const userData = { user_id: data.user_id, email: data.email };
        setUser(userData);
        onUserChange?.(userData);

        const savedChatId = getActiveChatId();
        if (savedChatId) {
          const loaded = await loadChatMessages(savedChatId);
          if (loaded) {
            setActiveChatIdState(savedChatId);
            await loadChatLayers(savedChatId);
          } else {
            clearActiveChatId();
          }
        }
      } catch {
        clearToken();
        clearActiveChatId();
      } finally {
        setAuthChecked(true);
      }
    }
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load chat list when history tab opens
  useEffect(() => {
    if (activeTab === 'history' && user && !chatsLoaded && !chatsLoading) {
      refreshChatList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, user, chatsLoaded, chatsLoading]);

  // Helpers

  const refreshChatList = useCallback(async () => {
    setChatsLoading(true);
    setChatListError('');
    try {
      const res = await apiFetch('/api/chats');
      if (!res.ok) {
        setChatListError('Kunne ikke laste tidligere samtaler.');
        return;
      }
      const data = await res.json();
      setChats(data.chats || []);
    } catch {
      setChatListError('Kunne ikke laste tidligere samtaler.');
    } finally {
      setChatsLoaded(true);
      setChatsLoading(false);
    }
  }, []);

  async function loadChatMessages(chatId) {
    try {
      const res = await apiFetch(`/api/chats/${chatId}/messages`);
      if (!res.ok) return false;
      const data = await res.json();
      const loaded = (data.messages || []).map(m => {
        const metadata = m.metadata || {};
        const msg = {
          role: m.role,
          text: m.content || '',
          attachments: [],
        };
        if (m.role === 'assistant' && metadata.thinking) {
          msg.thinking = metadata.thinking;
        }
        if (m.role === 'assistant' && metadata.turn_usage) {
          msg.turnUsage = metadata.turn_usage;
        }
        if (metadata.tool_hints?.length) {
          msg.tools = metadata.tool_hints.map(mcpId => {
            const entry = _TOOL_BY_MCP_ID[mcpId];
            return { name: entry?.name || mcpId, mcpTool: mcpId };
          });
        }
        return msg;
      });
      setMessages(loaded);
      return true;
    } catch {
      // Silently ignore.
      return false;
    }
  }

  async function loadChatLayers(chatId) {
    try {
      const res = await apiFetch(`/api/chats/${chatId}/layers`);
      if (!res.ok) return;
      const data = await res.json();
      const loaded = (data.layers || []).map(l => ({
        id: l.layer_id,
        name: l.name,
        shape: l.shape,
        visible: l.visible,
        geoJson: l.geojson,
      }));
      onSetDrawnLayers?.(loaded);
    } catch {
      // Non-critical; layers stay empty.
    }
  }

  function handleAuthSuccess(userData) {
    setUser(userData);
    setActiveChatIdState(null);
    setActiveTab('chat');
    setMessages([]);
    setChats([]);
    setChatsLoaded(false);
    setChatsLoading(false);
    setChatListError('');
    setUsageSession(null);
    setUsageMonthly(null);
    onUserChange?.(userData);
  }

  async function handleNewChat() {
    streamAbortRef.current?.abort();
    resetAutoFollow();
    setActiveChatIdState(null);
    setActiveChatId(null);
    setMessages([]);
    setInput('');
    setAttachments([]);
    setActiveTab('chat');
    setUsageSession(null);
    setUsageMonthly(null);
    onSetDrawnLayers?.([]);
  }

  async function handleContinueChat(chatId) {
    streamAbortRef.current?.abort();
    resetAutoFollow();
    const loaded = await loadChatMessages(chatId);
    if (!loaded) return;
    setActiveChatIdState(chatId);
    setActiveChatId(chatId);
    setActiveTab('chat');
    // Load persisted layers for this chat.
    await loadChatLayers(chatId);
    // Fetch current usage for this chat if a tracker exists on the backend.
    setUsageSession(null);
    setUsageMonthly(null);
    try {
      const res = await apiFetch(`/api/usage?chat_id=${chatId}`);
      if (res.ok) {
        const d = await res.json();
        if (d.usage) {
          setUsageSession(d.usage.session || null);
          setUsageMonthly(d.usage.monthly || null);
        }
      }
    } catch {
      // Non-critical; usage will repopulate on next message.
    }
  }

  async function handleDeleteManyChats(chatIds) {
    const results = await Promise.allSettled(
      chatIds.map(id => apiFetch(`/api/chats/${id}`, { method: 'DELETE' }))
    );
    const deletedIds = results.flatMap((result, index) => {
      if (result.status === 'fulfilled' && result.value.ok) {
        return chatIds[index];
      }
      return [];
    });

    if (deletedIds.includes(activeChatId)) {
      setActiveChatIdState(null);
      setActiveChatId(null);
      setMessages([]);
      setUsageSession(null);
      setUsageMonthly(null);
    }

    if (deletedIds.length > 0) {
      setChats(prev => prev.filter(c => !deletedIds.includes(c.id)));
    }
  }

  // Send message

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed && attachments.length === 0) return;
    if (isLoading) return;

    const wasNewChat = !activeChatId;
    const sentTools = [...selectedTools];
    const userMessage = { role: 'user', text: trimmed, attachments: [...attachments], tools: sentTools };
    resetAutoFollow();
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setAttachments([]);
    onClearSelectedTools?.();
    setIsLoading(true);
    let hadError = false;
    onAiStatusChange?.('active');

    // Add a placeholder assistant message that we'll update incrementally
    setMessages(prev => {
      assistantIdx.current = prev.length;
      return [...prev, { role: 'assistant', text: '', thinking: '', thinkingDone: false, streamDone: false, attachments: [] }];
    });

    try {
      const abortController = new AbortController();
      streamAbortRef.current = abortController;
      const res = await apiFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: trimmed,
          chat_id: activeChatId || undefined,
          map_context: drawnLayers,
          tool_hints: sentTools.map(t => t.mcpTool),
          stream: true,
        }),
        signal: abortController.signal,
      });

      if (!res.ok) {
        const data = await res.json();
        setMessages(prev => {
          const copy = [...prev];
          copy[assistantIdx.current] = { role: 'assistant', text: data.error || 'En feil oppstod.', attachments: [] };
          return copy;
        });
        hadError = true;
        return;
      }

      // Parse SSE stream
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let eventType = null;
      let sawThinking = false;
      let answerStarted = false;
      let pendingAnswerText = '';
      let answerFlushFrame = null;

      function appendAssistantText(content) {
        if (!content) return;
        setMessages(prev => {
          const idx = assistantIdx.current;
          if (idx === null || idx >= prev.length) return prev;
          const copy = [...prev];
          const msg = { ...copy[idx] };
          msg.text = (msg.text || '') + content;
          copy[idx] = msg;
          return copy;
        });
      }

      function flushPendingAnswerText() {
        if (!pendingAnswerText) return;
        const content = pendingAnswerText;
        pendingAnswerText = '';
        appendAssistantText(content);
      }

      function scheduleAnswerTextFlush() {
        if (answerFlushFrame !== null) return;
        answerFlushFrame = requestAnimationFrame(() => {
          answerFlushFrame = requestAnimationFrame(() => {
            answerFlushFrame = null;
            flushPendingAnswerText();
          });
        });
      }

      function cancelScheduledAnswerTextFlush() {
        if (answerFlushFrame === null) return;
        cancelAnimationFrame(answerFlushFrame);
        answerFlushFrame = null;
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ') && eventType) {
            let payload;
            try {
              payload = JSON.parse(line.slice(6));
            } catch {
              eventType = null;
              continue;
            }

            if (eventType === 'meta' && payload.chat_id) {
              if (!activeChatId) {
                setActiveChatIdState(payload.chat_id);
                setActiveChatId(payload.chat_id);
                setChatsLoaded(false);
                setChatsLoading(false);
                setChatListError('');

                // Bulk-persist any pre-existing drawn layers to the newly created chat.
                const persistable = drawnLayers.filter(l => l.id && l.geoJson);
                if (persistable.length > 0) {
                  apiFetch(`/api/chats/${payload.chat_id}/layers/bulk`, {
                    method: 'POST',
                    body: JSON.stringify({
                      layers: persistable.map(l => ({
                        layer_id: l.id,
                        name: l.name || 'Untitled layer',
                        shape: l.shape || 'Feature',
                        visible: l.visible !== false,
                        geojson: l.geoJson,
                      })),
                    }),
                  }).catch(() => { /* fire-and-forget */ });
                }
              }
            } else if (eventType === 'thinking') {
              sawThinking = true;
              setMessages(prev => {
                const idx = assistantIdx.current;
                if (idx === null || idx >= prev.length) return prev;
                const copy = [...prev];
                const msg = { ...copy[idx] };
                msg.thinking = appendThinkingChunk(msg.thinking, payload.content);
                msg.thinkingDone = false;
                copy[idx] = msg;
                return copy;
              });
            } else if (eventType === 'delta') {
              if (!answerStarted) {
                answerStarted = true;
                setMessages(prev => {
                  const idx = assistantIdx.current;
                  if (idx === null || idx >= prev.length) return prev;
                  const copy = [...prev];
                  const msg = { ...copy[idx] };
                  msg.thinkingDone = true;
                  copy[idx] = msg;
                  return copy;
                });
              }

              if (sawThinking) {
                pendingAnswerText += payload.content || '';
                scheduleAnswerTextFlush();
              } else {
                appendAssistantText(payload.content);
              }
            } else if (eventType === 'done') {
              cancelScheduledAnswerTextFlush();
              flushPendingAnswerText();
              // Process map actions
              if (payload.map_actions?.length && onLayerCreated) {
                payload.map_actions.forEach(action => {
                  const geojson = action.geojson;
                  const shape = geojson?.type === 'FeatureCollection'
                    ? 'FeatureCollection'
                    : (geojson?.geometry?.type || 'Feature');
                  onLayerCreated({
                    id: action.layer_id || `drawn-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                    name: action.layer_name,
                    shape,
                    geoJson: geojson,
                    visible: true,
                  }, { persisted: !!action.layer_id });
                });
              }

              if (payload.usage) {
                setUsageSession(payload.usage.session || null);
                setUsageMonthly(payload.usage.monthly || null);
              }

              // Finalize the assistant message with complete content and usage
              setMessages(prev => {
                const idx = assistantIdx.current;
                if (idx === null || idx >= prev.length) return prev;
                const copy = [...prev];
                const msg = { ...copy[idx] };
                msg.text = payload.content || msg.text;
                msg.turnUsage = payload.usage?.turn || null;
                msg.thinkingDone = true;
                msg.streamDone = true;
                copy[idx] = msg;
                return copy;
              });
              // Clear the now-dead ID so follow-up messages don't 404.
              if (payload.chat_deleted && wasNewChat) {
                setActiveChatIdState(null);
                setActiveChatId(null);
              }
            } else if (eventType === 'error') {
              hadError = true;
              setMessages(prev => {
                const idx = assistantIdx.current;
                if (idx === null || idx >= prev.length) return prev;
                const copy = [...prev];
                copy[idx] = {
                  role: 'assistant',
                  text: payload.error || 'En feil oppstod.',
                  attachments: [],
                };
                return copy;
              });
              // If persistence failed for a newly created chat, the server
              // deleted it — clear the now-dead ID so follow-ups don't 404.
              if (wasNewChat) {
                setActiveChatIdState(null);
                setActiveChatId(null);
              }
            }
            eventType = null;
          }
        }
      }
    } catch (err) {
      if (err?.name === 'AbortError') return; // component unmounted — nothing to update
      hadError = true;
      setMessages(prev => {
        const copy = [...prev];
        if (assistantIdx.current !== null && assistantIdx.current < copy.length) {
          copy[assistantIdx.current] = {
            role: 'assistant', text: 'Kunne ikke kontakte serveren.', attachments: [],
          };
        }
        return copy;
      });
      // If a new chat was created (meta event received) but the stream then
      // died, clear the now-dead chat_id so follow-up messages don't 404.
      if (wasNewChat) {
        setActiveChatIdState(null);
        setActiveChatId(null);
      }
    } finally {
      streamAbortRef.current = null;
      setIsLoading(false);
      onAiStatusChange?.(hadError ? 'error' : 'idle');
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    const newAttachments = files.map(file => {
      const isImage = file.type.startsWith('image/');
      return {
        id: crypto.randomUUID(),
        file,
        name: file.name,
        size: file.size,
        type: file.type,
        preview: isImage ? URL.createObjectURL(file) : null,
      };
    });
    setAttachments(prev => [...prev, ...newAttachments]);
    e.target.value = '';
  }

  function removeAttachment(id) {
    setAttachments(prev => {
      const item = prev.find(a => a.id === id);
      if (item?.preview) URL.revokeObjectURL(item.preview);
      return prev.filter(a => a.id !== id);
    });
  }

  // Render

  if (!authChecked) {
    return (
      <div className="chat-interface">
        <div className="chat-loading">Laster…</div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      {/* Auth overlay */}
      {!user && <AuthModal onSuccess={handleAuthSuccess} />}

      {/* Tab bar */}
      <div className="chat-tabs">
        <button
          className={`chat-tab${activeTab === 'chat' ? ' chat-tab--active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          Samtale
        </button>

        <button
          className={`chat-tab${activeTab === 'history' ? ' chat-tab--active' : ''}`}
          onClick={() => {
            setActiveTab('history');
            if (user && !chatsLoaded) refreshChatList();
          }}
        >
          Historikk
        </button>

        {user && (
          <button
            className="chat-tab-new-btn"
            title="Ny samtale"
            onClick={handleNewChat}
            aria-label="Ny samtale"
          >
            <Plus size={14} />
            <span>Ny samtale</span>
          </button>
        )}
      </div>

      {/* Samtale tab */}
      {activeTab === 'chat' && (
        <>
          <div className="chat-messages" ref={messagesRef}>
            {messages.length === 0 ? (
              <p className="chat-empty">Start samtalen…</p>
            ) : (
              messages.map((msg, i) => {
                const images = msg.attachments?.filter(att => att.preview) || [];
                const files  = msg.attachments?.filter(att => !att.preview) || [];
                const tools  = msg.tools || [];
                const hasText = !!msg.text;

                return (
                  <div key={i} className={`message-wrapper message-wrapper--${msg.role}`}>
                    {(images.length > 0 || files.length > 0 || tools.length > 0) && (
                      <div className="message-attachments-wrapper">
                        {images.length > 0 && (
                          <div className={`message-image-attachments ${hasText || images.length > 1 ? 'message-image-attachments--preview' : ''}`}>
                            {images.map(att => (
                              <div key={att.id} className="attachment-image">
                                <img src={att.preview} alt={att.name} />
                              </div>
                            ))}
                          </div>
                        )}
                        {files.length > 0 && (
                          <div className={`message-file-attachments ${hasText || files.length > 1 ? 'message-file-attachments--preview' : ''}`}>
                            {files.map(att => (
                              <div key={att.id} className="attachment-card">
                                <div className="attachment-file-icon"><FileText size={26} /></div>
                                <span className="attachment-file-name">{att.name}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {tools.length > 0 && (
                          <div className="message-tool-attachments">
                            {tools.map(tool => (
                              <div key={tool.name} className="tool-chip tool-chip--sent">
                                <Wrench size={13} />
                                <span>{tool.name}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    {msg.role === 'assistant' && msg.thinking && (
                      <ThinkingBlock thinking={msg.thinking} isStreaming={isLoading && !msg.thinkingDone && !msg.streamDone && i === messages.length - 1} />
                    )}
                    {hasText && (
                      <div className={`chat-bubble chat-bubble--${msg.role}`}>
                        {msg.role === 'assistant'
                          ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
                          : msg.text}
                      </div>
                    )}
                    {msg.role === 'assistant' && !hasText && isLoading && i === messages.length - 1 && !msg.thinking && (
                      <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                      </div>
                    )}
                    {msg.role === 'assistant' && msg.turnUsage && (
                      <>
                        <TurnSources toolCalls={msg.turnUsage?.tool_calls} />
                        <TurnUsage usage={msg.turnUsage} />
                      </>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {(attachments.length > 0 || selectedTools.length > 0) && (
            <div className="attachment-preview-strip">
              {selectedTools.map(tool => {
                const Icon = tool.icon;
                return (
                  <div key={`tool-${tool.name}`} className="attachment-card attachment-card--tool">
                    <button className="attachment-remove" onClick={() => onRemoveTool?.(tool)}>
                      <X size={14} />
                    </button>
                    <div className="attachment-tool-icon">
                      {typeof Icon === 'function' ? <Icon size={26} strokeWidth={1.8} /> : <Wrench size={26} />}
                    </div>
                    <div className="attachment-info">
                      <span className="attachment-name">{tool.name}</span>
                      <span className="attachment-size">Verktøy</span>
                    </div>
                  </div>
                );
              })}
              {attachments.map(att => (
                <div key={att.id} className="attachment-card">
                  <button className="attachment-remove" onClick={() => removeAttachment(att.id)}>
                    <X size={14} />
                  </button>
                  {att.preview
                    ? <img src={att.preview} alt={att.name} className="attachment-thumb" />
                    : <div className="attachment-file-icon"><FileText size={28} /></div>}
                  <div className="attachment-info">
                    <span className="attachment-name">{att.name}</span>
                    <span className="attachment-size">{(att.size / 1024).toFixed(1)} KB</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Unified session + monthly usage strip above input */}
          <InputAreaUsageBar monthly={usageMonthly} session={usageSession} />

          <div className="chat-input-area">
            <div className="paperclip">
              <button onClick={() => fileInputRef.current?.click()}><Paperclip size={18} /></button>
              <input
                type="file"
                style={{ display: 'none' }}
                ref={fileInputRef}
                accept="image/*, .pdf, .jpg, .jpeg, .png, .doc, .txt"
                multiple
                onChange={handleFileSelect}
              />
            </div>
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Skriv en melding…"
              disabled={isLoading || !user}
            />
            <button onClick={handleSend} disabled={isLoading || !user}>
              <ArrowUp size={18} />
            </button>
          </div>
        </>
      )}

      {activeTab === 'history' && (
        <ChatHistory
          chats={chats}
          activeChatId={activeChatId}
          isLoaded={chatsLoaded}
          loadError={chatListError}
          onContinue={handleContinueChat}
          onDeleteMany={handleDeleteManyChats}
          onRetryLoad={refreshChatList}
        />
      )}
    </div>
  );
}
