/**
 * Clinderma Embeddable Customer Support Chat Widget — V3.1
 * Includes:
 *   - Automatic Skin Assessment Form Isolation logic
 *   - Durable chat and identity persistence (localStorage)
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

  // 2. Widget State with durable browser storage
  let currentLang = localStorage.getItem('clinderma_chat_lang') || sessionStorage.getItem('clinderma_chat_lang') || 'en';
  let sessionId = sessionStorage.getItem('clin_session_id') || localStorage.getItem('clinderma_chat_session_id') || sessionStorage.getItem('clinderma_chat_session_id');
  if (!sessionId) {
    sessionId = 'session_' + (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2));
  }
  localStorage.setItem('clinderma_chat_session_id', sessionId);
  sessionStorage.setItem('clin_session_id', sessionId);
  localStorage.setItem('clinderma_chat_lang', currentLang);
  let savedPhone = localStorage.getItem('clinderma_chat_phone') || '';
  let phoneRequired = !savedPhone && localStorage.getItem('clinderma_phone_required') === 'true';
  let isOpen = false;
  let hasTrackedOpen = false;
  let lastLiveUpdateId = Number(localStorage.getItem('clinderma_chat_last_live_update_id')) || 0;
  let isSyncingLiveUpdates = false;
  let inactivityTimer = null;
  let inactivityEndTimer = null;
  let awaitingContinuation = false;
  let isPromptingContinuation = false;
  let chatEnded = false;
  let hasChatStarted = localStorage.getItem('clinderma_chat_started') === 'true';
  const INACTIVITY_PROMPT_MS = 2 * 60 * 1000;
  const INACTIVITY_END_MS = 30 * 1000;
  const API_HOST = window.location.origin;

  const skinTestLinks = {
    en: '[Take the Clinderma skin test](https://www.theclinderma.com/en/skin-test)',
    hi: '[क्लिंडरमा स्किन टेस्ट लें](https://www.theclinderma.com/hi/skin-test)',
    mr: '[क्लिंडरमा स्किन टेस्ट घ्या](https://www.theclinderma.com/mr/skin-test)'
  };

  function skinTestCta() {
    return skinTestLinks[currentLang] || skinTestLinks.en;
  }

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

  function starterHTML() {
    const selectedSkinLink = skinTestLinks[currentLang] || skinTestLinks.en;
    const selectedSkinUrl = selectedSkinLink.match(/\((.*?)\)/)[1];
    return `
    <div class="clin-msg clin-msg-bot">
      👋 Hi! Welcome to <strong>Clinderma</strong>.<br>
      Tell me what is happening with your skin. I can help with acne, pigmentation, treatment timelines, everyday skincare questions, and Clinderma product information.<br><br>
      <a href="${selectedSkinUrl}" target="_blank" style="color:#0284c7; text-decoration:underline; font-weight:500;">${currentLang === 'hi' ? 'क्लिंडरमा स्किन टेस्ट लें' : currentLang === 'mr' ? 'क्लिंडरमा स्किन टेस्ट घ्या' : 'Take the Clinderma skin test'}</a>
      <div class="clin-chips">
        <div class="clin-chip" data-query="How long will acne treatment take?">How long will acne treatment take?</div>
        <div class="clin-chip" data-query="What can help with dark spots?">What can help with dark spots?</div>
        <div class="clin-chip" data-query="Which Clinderma product may suit my concern?">Which Clinderma product may suit my concern?</div>
        <div class="clin-chip" data-query="How does Clinderma treatment work?">How does Clinderma treatment work?</div>
      </div>
    </div>
  `;
  }

  const savedHTML = localStorage.getItem('clinderma_chat_html') || sessionStorage.getItem('clinderma_chat_html');
  const initialMessagesHTML = savedHTML || starterHTML();

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
      sessionId = 'session_' + (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2));
      localStorage.setItem('clinderma_chat_session_id', sessionId);
      localStorage.removeItem('clinderma_chat_html');
      localStorage.removeItem('clinderma_chat_phone');
      localStorage.removeItem('clinderma_chat_last_live_update_id');
      savedPhone = '';
      phoneRequired = false;
      lastLiveUpdateId = 0;
      hasChatStarted = false;
      awaitingContinuation = false;
      setChatEnded(false);
      localStorage.setItem('clinderma_chat_started', 'false');
      localStorage.setItem('clinderma_phone_required', 'false');
      msgList.innerHTML = starterHTML();
      updatePhoneGate();
      saveChatState();
      resetInactivityCountdown();
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
      localStorage.setItem('clinderma_chat_lang', currentLang);
      const langLabel = currentLang === 'hi' ? 'हिंदी' : currentLang === 'mr' ? 'मराठी' : 'English';
      appendBotMsg(`Language set to <strong>${langLabel}</strong>. How can I help you?<br><br>${skinTestCta()}`);
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
      localStorage.setItem('clinderma_chat_html', clone.innerHTML);
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
      syncLiveUpdates();
      if (!hasTrackedOpen) {
        hasTrackedOpen = true;
        try {
          fetch(`${API_HOST}/api/analytics/event`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, event_type: 'chat_opened' })
          }).catch(function () {});
        } catch (e) {}
      }
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

  function appendLiveMessage(text, type) {
    const div = document.createElement('div');
    div.className = `clin-msg ${type === 'admin' ? 'clin-msg-admin' : 'clin-msg-system'}`;
    div.textContent = text;
    msgList.appendChild(div);
    msgList.scrollTop = msgList.scrollHeight;
    saveChatState();
  }

  function setChatEnded(ended) {
    chatEnded = ended;
    inputField.disabled = ended;
    sendBtn.disabled = ended;
    if (ended) {
      inputField.placeholder = 'Chat ended — select New to start again';
      clearTimeout(inactivityTimer);
      clearTimeout(inactivityEndTimer);
      inactivityTimer = null;
      inactivityEndTimer = null;
    } else {
      updatePhoneGate();
    }
  }

  function resetInactivityCountdown() {
    clearTimeout(inactivityTimer);
    clearTimeout(inactivityEndTimer);
    inactivityTimer = null;
    inactivityEndTimer = null;
    awaitingContinuation = false;
    if (!hasChatStarted || chatEnded) return;
    inactivityTimer = window.setTimeout(promptForContinuation, INACTIVITY_PROMPT_MS);
  }

  async function promptForContinuation() {
    if (chatEnded || !hasChatStarted || awaitingContinuation || isPromptingContinuation) return;
    isPromptingContinuation = true;
    try {
      const res = await fetch(`${API_HOST}/api/chat/${encodeURIComponent(sessionId)}/inactivity-prompt`, {
        method: 'POST'
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.status === 'ended') {
        setChatEnded(true);
        return;
      }
      if (data.status === 'expired') {
        awaitingContinuation = true;
        await endChatForInactivity();
        return;
      }
      if (data.status !== 'awaiting_confirmation') {
        inactivityTimer = window.setTimeout(promptForContinuation, 1000);
        return;
      }
      awaitingContinuation = true;
      if (data.message) appendBotMsg(data.message);
      inactivityEndTimer = window.setTimeout(endChatForInactivity, INACTIVITY_END_MS);
    } catch (err) {
      console.warn('[Clinderma Chat] Could not send inactivity prompt:', err);
    } finally {
      isPromptingContinuation = false;
    }
  }

  async function endChatForInactivity() {
    if (!awaitingContinuation || chatEnded) return;
    try {
      await fetch(`${API_HOST}/api/chat/${encodeURIComponent(sessionId)}/end`, { method: 'POST' });
      await syncLiveUpdates();
    } catch (err) {
      console.warn('[Clinderma Chat] Could not close inactive chat:', err);
    } finally {
      awaitingContinuation = false;
      setChatEnded(true);
    }
  }

  async function syncLiveUpdates() {
    if (!isOpen || isSyncingLiveUpdates) return;
    isSyncingLiveUpdates = true;
    try {
      const res = await fetch(
        `${API_HOST}/api/chat/${encodeURIComponent(sessionId)}/updates?after_id=${lastLiveUpdateId}`
      );
      if (!res.ok) return;
      const data = await res.json();
      (data.updates || []).forEach((update) => {
        const isAdmin = update.sender && update.sender.indexOf('admin:') === 0;
        appendLiveMessage(
          isAdmin ? `Clinderma Care Team: ${update.message}` : update.message,
          isAdmin ? 'admin' : 'system'
        );
        lastLiveUpdateId = Math.max(lastLiveUpdateId, Number(update.id) || 0);
      });
      if (data.last_id !== undefined) {
        lastLiveUpdateId = Math.max(lastLiveUpdateId, Number(data.last_id) || 0);
      }
      if (data.chat_status === 'ended') {
        setChatEnded(true);
      } else if (data.chat_status === 'expired') {
        awaitingContinuation = true;
        await endChatForInactivity();
      } else if (data.chat_status === 'idle') {
        await promptForContinuation();
      } else if (data.chat_status === 'awaiting_confirmation') {
        awaitingContinuation = true;
        if (!inactivityEndTimer) {
          const promptedAt = data.inactivity_prompted_at ? new Date(data.inactivity_prompted_at).getTime() : Date.now();
          const remaining = Math.max(0, INACTIVITY_END_MS - (Date.now() - promptedAt));
          inactivityEndTimer = window.setTimeout(endChatForInactivity, remaining);
        }
      }
      localStorage.setItem('clinderma_chat_last_live_update_id', String(lastLiveUpdateId));
    } catch (err) {
      // Live updates are supplementary; normal chat remains usable if polling fails.
      console.warn('[Clinderma Chat] Could not fetch live updates:', err);
    } finally {
      isSyncingLiveUpdates = false;
    }
  }

  function appendSuggestions(questions) {
    if (!Array.isArray(questions) || !questions.length || phoneRequired) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'clin-chips';
    questions.forEach((question) => {
      const chip = document.createElement('div');
      chip.className = 'clin-chip';
      chip.setAttribute('data-query', question);
      chip.textContent = question;
      wrapper.appendChild(chip);
    });
    msgList.appendChild(wrapper);
    msgList.scrollTop = msgList.scrollHeight;
    saveChatState();
  }

  function validPhone(text) {
    const match = String(text || '').match(/(?:^|\D)(?:(?:\+91|0)[-\s]?)?[6-9]\d{9}(?!\d)/);
    return match ? match[0] : '';
  }

  function updatePhoneGate() {
    inputField.placeholder = phoneRequired
      ? 'Your name & WhatsApp number (e.g. Ananya 9876543210)...'
      : 'Ask a skincare question...';
    localStorage.setItem('clinderma_phone_required', String(phoneRequired));
  }

  async function handleSend() {
    const txt = inputField.value.trim();
    if (!txt || chatEnded) return;

    const isContinuationReply = awaitingContinuation;
    hasChatStarted = true;
    localStorage.setItem('clinderma_chat_started', 'true');
    resetInactivityCountdown();

    if (phoneRequired && !isContinuationReply && !validPhone(txt)) {
      appendBotMsg(`To help our Skin Coach connect with you, please share your 10-digit WhatsApp number (you can also include your name, e.g. "Ananya 9876543210").<br><br>${skinTestCta()}`);
      inputField.focus();
      return;
    }

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
          channel: 'website',
          user_phone: savedPhone || null
        })
      });

      const data = await res.json();
      const typingElem = document.getElementById('clin-typing');
      if (typingElem) typingElem.remove();

      if (data && data.captured_phone) {
        savedPhone = data.captured_phone;
        localStorage.setItem('clinderma_chat_phone', savedPhone);
      }

      phoneRequired = Boolean(data && data.requires_phone && !savedPhone);
      updatePhoneGate();

      if (data && data.answer) {
        appendBotMsg(data.answer);
      }
      if (data && data.phone_prompt && phoneRequired) {
        appendBotMsg(data.phone_prompt);
      }
      if (data && !phoneRequired) {
        appendSuggestions(data.suggested_questions);
      }
      if (data && data.taken_over) {
        // The bot is intentionally silent while an admin is handling the chat.
        syncLiveUpdates();
      } else if (!data || (!data.answer && !data.phone_prompt)) {
        appendBotMsg(`I'm sorry, I am currently unable to process that. Please try again.<br><br>${skinTestCta()}`);
      }
      resetInactivityCountdown();
    } catch (err) {
      console.error('[Clinderma Chat Error]', err);
      const typingElem = document.getElementById('clin-typing');
      if (typingElem) typingElem.remove();
      appendBotMsg(`Connection error. Please check your network or try again.<br><br>${skinTestCta()}`);
    }
  }

  updatePhoneGate();
  resetInactivityCountdown();
  window.setInterval(syncLiveUpdates, 3500);
})();
