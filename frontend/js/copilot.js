/**
 * copilot.js – AI Copilot chat UI logic.
 */

// ─── State ────────────────────────────────────────────────────────────────────
let isThinking = false;

// ─── Render helpers ───────────────────────────────────────────────────────────
function markdownToHtml(text) {
  // Very lightweight markdown → HTML converter
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code style="background:rgba(255,255,255,0.08);padding:1px 5px;border-radius:4px;font-size:0.85em">$1</code>')
    .replace(/^#{1,3}\s+(.+)$/gm, '<strong>$1</strong>')
    .replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

function appendMessage(role, content, extraHtml = '') {
  const messages = document.getElementById('chat-messages');
  if (!messages) return;

  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;

  const html = markdownToHtml(content);
  div.innerHTML = `
    <div class="msg-bubble">
      <p>${html}</p>
      ${extraHtml}
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function appendThinking() {
  const messages = document.getElementById('chat-messages');
  if (!messages) return;

  const div = document.createElement('div');
  div.className = 'chat-msg assistant';
  div.id = 'thinking-indicator';
  div.innerHTML = `
    <div class="msg-bubble">
      <div class="thinking-dots">
        <span></span><span></span><span></span>
      </div>
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function removeThinking() {
  const el = document.getElementById('thinking-indicator');
  if (el) el.remove();
}

function buildDataPanel(data) {
  if (!data || Object.keys(data).length === 0) return '';
  const text = JSON.stringify(data, null, 2);
  return `
    <details style="margin-top:12px">
      <summary style="font-size:0.72rem;color:var(--text-muted);cursor:pointer;user-select:none">
        📊 View supporting data
      </summary>
      <div class="data-panel">${text}</div>
    </details>
  `;
}

// ─── Send message ─────────────────────────────────────────────────────────────
async function sendCopilotMessage(question) {
  if (!question.trim() || isThinking) return;

  isThinking = true;
  const sendBtn = document.getElementById('chat-send');
  const input = document.getElementById('chat-input');
  if (sendBtn) sendBtn.disabled = true;
  if (input) input.value = '';

  // Show user message
  appendMessage('user', question);

  // Show thinking indicator
  appendThinking();

  try {
    const result = await API.askCopilot(question);
    removeThinking();

    // Update header tagline based on model returned
    const tagline = document.getElementById('copilot-tagline');
    if (tagline) {
      if (result.model && result.model.toLowerCase().includes('gemini') && !result.error) {
        tagline.textContent = 'Powered by Gemini · Grounded in your data';
      } else {
        tagline.textContent = 'Deterministic fallback · Grounded in your data';
      }
    }

    const dataPanel = buildDataPanel(result.data);
    appendMessage('assistant', result.answer, dataPanel);

    // If error (e.g. missing API key), still show it as an info message
    if (result.error && result.error !== 'missing_api_key') {
      console.warn('Copilot error:', result.error);
    }

  } catch (err) {
    removeThinking();
    appendMessage('assistant',
      `⚠️ Could not get a response: ${err.message}. Please try again.`
    );
  } finally {
    isThinking = false;
    if (sendBtn) sendBtn.disabled = false;
    if (input) input.focus();
  }
}

// ─── Init chat UI ─────────────────────────────────────────────────────────────
function initCopilot() {
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');

  if (sendBtn) {
    sendBtn.addEventListener('click', () => {
      const q = input ? input.value.trim() : '';
      if (q) sendCopilotMessage(q);
    });
  }

  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const q = input.value.trim();
        if (q) sendCopilotMessage(q);
      }
    });
  }

  // Suggestion buttons (event delegation on chat-messages)
  const messages = document.getElementById('chat-messages');
  if (messages) {
    messages.addEventListener('click', (e) => {
      const btn = e.target.closest('.suggestion-btn');
      if (btn) {
        sendCopilotMessage(btn.dataset.q);
      }
    });
  }
}
