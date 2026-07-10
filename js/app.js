/**
 * WellnessAI – Main Application JavaScript
 * Handles: dark mode, response parsing, planner rendering, shared utilities
 */

const WellnessApp = (() => {

  // ── Dark Mode ────────────────────────────────────────────────────────────
  const html        = document.documentElement;
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon   = document.getElementById('themeIcon');

  function applyTheme(theme) {
    html.setAttribute('data-theme', theme);
    localStorage.setItem('wa-theme', theme);
    if (themeIcon) {
      themeIcon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
  }

  // Load saved theme
  const savedTheme = localStorage.getItem('wa-theme') || 'light';
  applyTheme(savedTheme);

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      applyTheme(html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });
  }

  // ── Response Parser ──────────────────────────────────────────────────────
  /**
   * Converts raw Orchestrate markdown-ish text into structured HTML.
   * Handles ## headings, - bullets, and plain paragraphs.
   */
  function parseResponse(text) {
    if (!text) return '<p class="text-muted">No response.</p>';

    // Check if this is a planner-format response (contains ### Morning etc.)
    if (/###\s*(Morning|Afternoon|Evening|Night)/i.test(text)) {
      return renderPlanner(text);
    }

    const lines = text.split('\n');
    let html = '';
    let inList = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) {
        if (inList) { html += '</ul>'; inList = false; }
        continue;
      }

      // ## Heading (section title)
      if (/^##\s+/.test(line)) {
        if (inList) { html += '</ul>'; inList = false; }
        const title = line.replace(/^##\s+/, '');
        const iconMap = {
          'Overview':       '📋',
          'Symptoms':       '🩺',
          'Precautions':    '🛡️',
          'Suggested Diet': '🥗',
          'Diet':           '🥗',
          'Note':           '⚕',
          'Notes':          '⚕',
        };
        const icon = Object.keys(iconMap).find(k => title.toLowerCase().includes(k.toLowerCase()));
        html += `<div class="response-section">
          <div class="response-section-title">${iconMap[icon] || '•'} ${escapeHtml(title)}</div>`;
        // We'll close this div after the content — track it
        continue;
      }

      // ### Sub-heading
      if (/^###\s+/.test(line)) {
        if (inList) { html += '</ul>'; inList = false; }
        html += `<strong>${escapeHtml(line.replace(/^###\s+/, ''))}</strong><br>`;
        continue;
      }

      // Bullet point
      if (/^[-*•]\s+/.test(line)) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${escapeHtml(line.replace(/^[-*•]\s+/, ''))}</li>`;
        continue;
      }

      // ⚕ Note / disclaimer line
      if (line.startsWith('⚕') || line.toLowerCase().includes('medical advice') || line.toLowerCase().includes('consult a')) {
        if (inList) { html += '</ul>'; inList = false; }
        html += `<div class="response-note">${escapeHtml(line)}</div>`;
        continue;
      }

      // Regular paragraph
      if (inList) { html += '</ul>'; inList = false; }
      html += `<p>${escapeHtml(line)}</p>`;
    }

    if (inList) html += '</ul>';

    // Wrap in response-overview if nothing was structured
    if (!html.includes('response-section') && !html.includes('<ul>')) {
      return `<div class="response-overview">${html}</div>`;
    }

    return html;
  }

  // ── Planner Renderer ─────────────────────────────────────────────────────
  /**
   * Renders a daily planner response (Morning/Afternoon/Evening/Night) into
   * time-block cards.
   */
  function renderPlanner(text, conditionLabel, goalLabel) {
    const sections = {
      morning:   { emoji: '🌅', label: 'Morning', key: 'morning',   content: [] },
      afternoon: { emoji: '☀️', label: 'Afternoon', key: 'afternoon', content: [] },
      evening:   { emoji: '🌆', label: 'Evening',  key: 'evening',  content: [] },
      night:     { emoji: '🌙', label: 'Night',    key: 'night',    content: [] },
      notes:     { emoji: '📝', label: 'Notes',    key: 'notes',    content: [] },
    };

    let currentSection = null;
    const lines = text.split('\n');

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      const header = trimmed.replace(/^#+\s*/, '').toLowerCase();
      if      (header.startsWith('morning'))   currentSection = 'morning';
      else if (header.startsWith('afternoon')) currentSection = 'afternoon';
      else if (header.startsWith('evening'))   currentSection = 'evening';
      else if (header.startsWith('night'))     currentSection = 'night';
      else if (header.startsWith('note'))      currentSection = 'notes';
      else if (currentSection) {
        sections[currentSection].content.push(trimmed);
      }
    }

    let html = '';

    // Header
    if (conditionLabel || goalLabel) {
      html += `<div class="planner-header mb-3">
        <h5 class="mb-1">🍽️ Daily Meal Plan</h5>
        ${conditionLabel ? `<span class="badge bg-primary-subtle text-primary me-2">${escapeHtml(conditionLabel)}</span>` : ''}
        ${goalLabel      ? `<span class="badge bg-success-subtle text-success">${escapeHtml(goalLabel)}</span>` : ''}
      </div>`;
    }

    // Time blocks
    const order = ['morning', 'afternoon', 'evening', 'night', 'notes'];
    for (const key of order) {
      const sec = sections[key];
      if (!sec.content.length) continue;

      const bodyHtml = renderPlannerContent(sec.content);
      const isNote   = key === 'notes';

      if (isNote) {
        html += `<div class="planner-note-box">
          ${sec.emoji} <strong>Notes & Disclaimer:</strong><br>${bodyHtml}
        </div>`;
      } else {
        html += `<div class="planner-time-block">
          <div class="time-block-header ${key}">${sec.emoji} ${sec.label}</div>
          <div class="time-block-body">${bodyHtml}</div>
        </div>`;
      }
    }

    if (!html) {
      // Fallback: just parse as regular response
      return parseResponse(text);
    }

    return html;
  }

  function renderPlannerContent(lines) {
    let html = '';
    let inList = false;
    for (const line of lines) {
      if (/^[-*•]\s+/.test(line)) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${escapeHtml(line.replace(/^[-*•]\s+/, ''))}</li>`;
      } else {
        if (inList) { html += '</ul>'; inList = false; }
        html += `<p>${escapeHtml(line)}</p>`;
      }
    }
    if (inList) html += '</ul>';
    return html;
  }

  // ── Utilities ─────────────────────────────────────────────────────────────
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Auto-dismiss disclaimer after 10s
  setTimeout(() => {
    const banner = document.getElementById('disclaimerBanner');
    if (banner) banner.style.transition = 'opacity .5s';
    // Don't auto-dismiss — keep visible for compliance
  }, 10000);

  // Pre-fill chat input from URL ?q=
  window.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
      const params = new URLSearchParams(location.search);
      const q = params.get('q');
      if (q) {
        chatInput.value = `Tell me about ${q} — symptoms, diet, and precautions.`;
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
      }
    }
  });

  return { parseResponse, renderPlanner, escapeHtml };
})();
