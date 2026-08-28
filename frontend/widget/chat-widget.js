/**
 * Clinderma Embeddable Customer Support Chat Widget — V3.1
 * Includes:
 *   - Automatic Skin Assessment Form Isolation logic
 *   - Session persistence across page reloads (sessionStorage)
 *   - Clear / New Chat session restart
 *   - Rich markdown rendering (bold, italics, links, line breaks)
 *   - Language bar (EN, HI, MR)
 */

(function () {
  // 1. ROUTE GUARD: Enforce form isolation
  const currentPath = window.location.pathname.toLowerCase();
  const currentHash = window.location.hash.toLowerCase();
  const isAssessmentPage =
    currentPath.includes('assessment') ||
    currentHash.includes('assessment') ||
    document.getElementById('skin-assessment-form') !== null;

  if (isAssessmentPage) {
    console.log('[Clinderma Chatbot] Widget suppressed on Skin Assessment Form route.');
    return; // Exit completely, never render widget
  }

  // 2. Widget State with Persistent Session Storage
  let currentLang = sessionStorage.getItem('clinderma_chat_lang') || 'en';
  let sessionId = sessionStorage.getItem('clinderma_chat_session_id');
  if (!sessionId) {
    sessionId = 'session_' + Math.random().toString(36).substring(2, 10);
    sessionStorage.setItem('clinderma_chat_session_id', sessionId);
  }
  let isOpen = false;
  const API_HOST = window.location.origin;

  // 3. Inject CSS Link if not present
  if (!document.getElementById('clinderma-widget-css')) {
    const link = document.createElement('link');
    link.id = 'clinderma-widget-css';
    link.rel = 'stylesheet';
    link.href = '/widget/chat-widget.css';
    document.head.appendChild(link);
  }

  // 4. Create Widget HTML Structure
  const launcher = document.createElement('button');
  launcher.id = 'clinderma-widget-launcher';
  launcher.setAttribute('aria-label', 'Open Support Chat');
  launcher.innerHTML = `
    <span class="clin-badge-dot"></span>
    <svg viewBox="0 0 24 24">
      <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/>
    </svg>
  `;

  const defaultStarterHTML = `
    <div class="clin-msg clin-msg-bot">
      👋 Hi! Welcome to <strong>Clinderma</strong>.<br>
      I can help you with acne & pigmentation treatment details, clinical skincare guides, order tracking, or connecting with a Skin Coach.
      <div class="clin-chips">
        <div class="clin-chip" data-query="What causes tiny bumps on my forehead?">Forehead Bumps</div>
        <div class="clin-chip" data-query="Do I need moisturizer if I have pimples?">Moisturizer & Acne</div>
        <div class="clin-chip" data-query="How long does acne treatment take?">Acne Timeline</div>
        <div class="clin-chip" data-query="Track order CLIN-1001">Track Order CLIN-1001</div>
        <div class="clin-chip" data-query="Talk to Skin Coach">Skin Coach Handoff</div>
      </div>
    </div>
  `;

  const savedHTML = sessionStorage.getItem('clinderma_chat_html');
  const initialMessagesHTML = savedHTML || defaultStarterHTML;

  const container = document.createElement('div');
  container.id = 'clinderma-chat-container';
  container.innerHTML = `
    <div class="clin-header">
      <div class="clin-header-info">
        <div class="clin-avatar">C</div>
        <div class="clin-title-box">
          <h4>Clinderma Assistant</h4>
          <span>Online | Dermatologist Support</span>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 6px;">
        <button class="clin-close-btn" id="clin-reset" title="Start New Chat" style="font-size: 13px; font-weight: normal; opacity: 0.85; padding: 2px 6px;">🔄 New</button>
        <button class="clin-close-btn" id="clin-close" title="Close Chat">&times;</button>
      </div>
    </div>

    <div class="clin-lang-bar">
      <span>Language / भाषा:</span>
      <div class="clin-lang-opts">
        <button class="clin-lang-btn ${currentLang === 'en' ? 'active' : ''}" data-lang="en">EN</button>
        <button class="clin-lang-btn ${currentLang === 'hi' ? 'active' : ''}" data-lang="hi">हिंदी</button>
        <button class="clin-lang-btn ${currentLang === 'mr' ? 'active' : ''}" data-lang="mr">मराठी</button>
      </div>
    </div>

    <div class="clin-messages" id="clin-msg-list">
      ${initialMessagesHTML}
    </div>

    <div class="clin-input-bar">
      <input type="text" class="clin-input" id="clin-input-field" placeholder="Ask a question or enter mobile no..." />
      <button class="clin-send-btn" id="clin-send-btn" aria-label="Send Message">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
        </svg>
      </button>
    </div>
  `;

  document.body.appendChild(launcher);
  document.body.appendChild(container);

  // 5. Event Listeners
  const msgList = document.getElementById('clin-msg-list');
  const inputField = document.getElementById('clin-input-field');
  const sendBtn = document.getElementById('clin-send-btn');
  const closeBtn = document.getElementById('clin-close');
  const resetBtn = document.getElementById('clin-reset');

  launcher.addEventListener('click', toggleChat);
  closeBtn.addEventListener('click', toggleChat);

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      sessionId = 'session_' + Math.random().toString(36).substring(2, 10);
      sessionStorage.setItem('clinderma_chat_session_id', sessionId);
      sessionStorage.removeItem('clinderma_chat_html');
      msgList.innerHTML = defaultStarterHTML;
      appendBotMsg("Started a new chat session. How can I help you today?");
    });
  }

  sendBtn.addEventListener('click', handleSend);
  inputField.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleSend();
  });

  // Language buttons
  document.querySelectorAll('.clin-lang-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.clin-lang-btn').forEach((b) => b.classList.remove('active'));
      e.target.classList.add('active');
      currentLang = e.target.getAttribute('data-lang');
      sessionStorage.setItem('clinderma_chat_lang', currentLang);
      const langLabel = currentLang === 'hi' ? 'हिंदी' : currentLang === 'mr' ? 'मराठी' : 'English';
      appendBotMsg(`Language set to <strong>${langLabel}</strong>. How can I help you?`);
    });
  });

  // Quick chip delegation
  msgList.addEventListener('click', (e) => {
    if (e.target.classList.contains('clin-chip')) {
      const q = e.target.getAttribute('data-query');
      inputField.value = q;
      handleSend();
    }
  });

  function saveChatState() {
    try {
      // Remove typing indicator before saving
      const clone = msgList.cloneNode(true);
      const typing = clone.querySelector('#clin-typing');
      if (typing) typing.remove();
      sessionStorage.setItem('clinderma_chat_html', clone.innerHTML);
    } catch (e) {
      console.warn('[Clinderma Chat] Could not persist chat state:', e);
    }
  }

  function toggleChat() {
    isOpen = !isOpen;
    if (isOpen) {
      container.classList.add('clin-open');
      inputField.focus();
      msgList.scrollTop = msgList.scrollHeight;
    } else {
      container.classList.remove('clin-open');
    }
  }

  function appendUserMsg(txt) {
    const div = document.createElement('div');
    div.className = 'clin-msg clin-msg-user';
    div.textContent = txt;
    msgList.appendChild(div);
    msgList.scrollTop = msgList.scrollHeight;
    saveChatState();
  }

  function appendBotMsg(html) {
    const div = document.createElement('div');
    div.className = 'clin-msg clin-msg-bot';

    // Enhanced markdown formatting
    let formatted = html
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" style="color:#0284c7; text-decoration:underline; font-weight:500;">$1</a>')
      .replace(/\n/g, '<br>');

    div.innerHTML = formatted;
    msgList.appendChild(div);
    msgList.scrollTop = msgList.scrollHeight;
    saveChatState();
  }

  async function handleSend() {
    const txt = inputField.value.trim();
    if (!txt) return;

    appendUserMsg(txt);
    inputField.value = '';

    // Show typing state
    const typingDiv = document.createElement('div');
    typingDiv.className = 'clin-msg clin-msg-bot';
    typingDiv.id = 'clin-typing';
    typingDiv.innerHTML = '<em>Clinderma Assistant is typing...</em>';
    msgList.appendChild(typingDiv);
    msgList.scrollTop = msgList.scrollHeight;

    try {
      const res = await fetch(`${API_HOST}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: txt,
          session_id: sessionId,
          language: currentLang,
          channel: 'website'
        })
      });

      const data = await res.json();
      const typingElem = document.getElementById('clin-typing');
      if (typingElem) typingElem.remove();

      if (data && data.answer) {
        appendBotMsg(data.answer);
      } else {
        appendBotMsg("I'm sorry, I am currently unable to process that. Please try again or talk to a Skin Coach.");
      }
    } catch (err) {
      console.error('[Clinderma Chat Error]', err);
      const typingElem = document.getElementById('clin-typing');
      if (typingElem) typingElem.remove();
      appendBotMsg("Connection error. Please check your network or try again.");
    }
  }
})();
