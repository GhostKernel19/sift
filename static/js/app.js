/**
 * Sift — Evidence Desk Frontend Controller
 * 
 * Strict Invariants:
 * 1. Security: NEVER use innerHTML. All text rendered via textContent / DOM APIs.
 * 2. Maintainer Supremacy: Never auto-post comments or actions. Copy draft only.
 * 3. Quote Verification: Visual distinction (text + icon) for verified vs quarantined quotes.
 * 4. Human-in-the-Loop Supremacy: Only human maintainers initiate actions.
 */

(function () {
  'use strict';

  // ============================================================================
  // DOM Safe Element Builders (Zero innerHTML Usage)
  // ============================================================================
  function createEl(tagName, classNames, text) {
    const el = document.createElement(tagName);
    if (classNames) {
      if (Array.isArray(classNames)) {
        classNames.forEach(c => c && el.classList.add(c));
      } else {
        el.className = classNames;
      }
    }
    if (text !== undefined && text !== null) {
      el.textContent = text;
    }
    return el;
  }

  function clearElement(el) {
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  // ============================================================================
  // Application State
  // ============================================================================
  const state = {
    currentRepo: null,
    currentPR: null,
    currentAssessment: null,
    currentDossier: null,
    isCached: false,
    isAnalyzing: false,
    lastAnalyzeTarget: null,
    activeEvidenceIndex: null,
    queue: [],
    loadingTimer: null
  };

  // DOM Element References
  const dom = {
    // Header
    modeIndicator: document.getElementById('mode-indicator'),
    modeIndicatorText: document.getElementById('mode-indicator-text'),
    healthIndicator: document.getElementById('health-indicator'),
    healthDot: document.getElementById('health-dot'),
    healthLabel: document.getElementById('health-label'),

    // Queue / Inputs
    prUrlInput: document.getElementById('pr-url-input'),
    btnAnalyze: document.getElementById('btn-analyze'),
    queueList: document.getElementById('queue-list'),
    queueCount: document.getElementById('queue-count'),

    // Desk Views
    stateEmpty: document.getElementById('state-empty'),
    stateLoading: document.getElementById('state-loading'),
    stateError: document.getElementById('state-error'),
    stateContent: document.getElementById('state-content'),
    stateModelUnavailable: document.getElementById('state-model-unavailable'),
    statePartialDataBanner: document.getElementById('state-partial-data-banner'),
    stateLiveFailureBanner: document.getElementById('state-live-failure-banner'),
    liveFailureText: document.getElementById('live-failure-text'),
    btnDismissLiveFailure: document.getElementById('btn-dismiss-live-failure'),
    partialDataTitle: document.getElementById('partial-data-title'),
    partialDataText: document.getElementById('partial-data-text'),
    btnDismissAlert: document.getElementById('btn-dismiss-alert'),
    btnErrorRetry: document.getElementById('btn-error-retry'),
    btnRerunLive: document.getElementById('btn-rerun-live'),
    errorMessageText: document.getElementById('error-message-text'),
    errorTitle: document.querySelector('#state-error .error-title'),
    errorDetailsContainer: document.getElementById('error-details-container'),
    errorDetailsCode: document.getElementById('error-details-code'),

    // Center Desk Toolbar & Cards
    dossierTypeBadge: document.getElementById('dossier-type-badge'),
    dossierSlug: document.getElementById('dossier-slug'),
    branchInfo: document.getElementById('branch-info'),
    dossierSourceTag: document.getElementById('dossier-source-tag'),
    viewOnGithubLink: document.getElementById('view-on-github-link'),
    prNumberBadge: document.getElementById('pr-number-badge'),
    prHeadlineText: document.getElementById('pr-headline-text'),
    prAuthorVal: document.getElementById('pr-author-val'),
    prAssocVal: document.getElementById('pr-assoc-val'),
    prStateVal: document.getElementById('pr-state-val'),
    prDeltaVal: document.getElementById('pr-delta-val'),
    prBodyContainer: document.getElementById('pr-body-container'),
    fileCountBadge: document.getElementById('file-count-badge'),
    changedFilesList: document.getElementById('changed-files-list'),
    diffFilePathText: document.getElementById('diff-file-path-text'),
    diffTruncationBadge: document.getElementById('diff-truncation-badge'),
    diffCodePanel: document.getElementById('diff-code-panel'),

    // Assessment Column
    assessmentEmptyState: document.getElementById('assessment-empty-state'),
    assessmentScrollArea: document.getElementById('assessment-scroll-area'),
    cardReplyDraft: document.getElementById('card-reply-draft'),
    assessorModelBadge: document.getElementById('assessor-model-badge'),
    badgeConfidence: document.getElementById('badge-confidence'),
    badgeRecommendation: document.getElementById('badge-recommendation'),
    recExplanationText: document.getElementById('rec-explanation-text'),
    priorityNumericText: document.getElementById('priority-numeric-text'),
    priorityProgressBar: document.getElementById('priority-progress-bar'),
    assessmentSummaryText: document.getElementById('assessment-summary-text'),
    evidenceCountBadge: document.getElementById('evidence-count-badge'),
    evidenceItemsContainer: document.getElementById('evidence-items-container'),
    missingContextList: document.getElementById('missing-context-list'),
    cardUncertainty: document.getElementById('card-uncertainty'),
    uncertaintyReasonText: document.getElementById('uncertainty-reason-text'),
    replyDraftTextarea: document.getElementById('reply-draft-textarea'),
    btnCopyDraft: document.getElementById('btn-copy-draft'),
    btnCopyDraftText: document.getElementById('btn-copy-draft-text'),
    btnResetDraft: document.getElementById('btn-reset-draft'),
    copyToast: document.getElementById('copy-toast'),

    // Footer
    footerDataSource: document.getElementById('footer-data-source'),
    footerTimestamp: document.getElementById('footer-timestamp'),
    footerModelName: document.getElementById('footer-model-name'),
    footerVerifiedBadge: document.getElementById('footer-verified-badge')
  };

  // ============================================================================
  // View State Management
  // ============================================================================
  function showViewState(viewName) {
    dom.stateEmpty.style.display = viewName === 'empty' ? 'flex' : 'none';
    dom.stateLoading.style.display = viewName === 'loading' ? 'flex' : 'none';
    dom.stateError.style.display = viewName === 'error' ? 'flex' : 'none';
    dom.stateContent.style.display = viewName === 'content' ? 'flex' : 'none';

    // Ensure right column never shows an assessment when center is in empty or error state
    if (viewName === 'error' || viewName === 'empty') {
      if (dom.assessmentEmptyState) dom.assessmentEmptyState.style.display = 'block';
      if (dom.assessmentScrollArea) dom.assessmentScrollArea.style.display = 'none';
      if (dom.cardReplyDraft) dom.cardReplyDraft.style.display = 'none';
      if (dom.footerVerifiedBadge) dom.footerVerifiedBadge.style.display = 'none';
    } else if (viewName === 'content') {
      if (dom.assessmentEmptyState) dom.assessmentEmptyState.style.display = 'none';
      if (dom.assessmentScrollArea) dom.assessmentScrollArea.style.display = 'block';
      if (dom.cardReplyDraft) dom.cardReplyDraft.style.display = 'block';
    }
  }

  // ============================================================================
  // Health & Model Status Check (Real Signal Tracking)
  // ============================================================================
  let currentGemmaModel = 'gemma-4-26b-a4b-it';

  function getModelDisplayName(model) {
    if (!model) return 'Gemma 4 (26b)';
    if (model.includes('26b')) return 'Gemma 4 (26b)';
    if (model.includes('31b')) return 'Gemma 4 (31b)';
    return model;
  }

  function setGemmaSignal(status, detail) {
    const modelName = getModelDisplayName(currentGemmaModel);
    if (!dom.healthDot || !dom.healthLabel) return;
    if (status === 'online') {
      dom.healthDot.className = 'health-dot dot-online';
      dom.healthLabel.textContent = `${modelName}: Online`;
      if (dom.healthIndicator) dom.healthIndicator.setAttribute('title', `Live Gemma inference succeeded (${currentGemmaModel})`);
    } else if (status === 'unchecked') {
      dom.healthDot.className = 'health-dot dot-unchecked';
      dom.healthLabel.textContent = `${modelName}: Not yet called`;
      if (dom.healthIndicator) dom.healthIndicator.setAttribute('title', `Backend ready; no live Gemma inference evaluated yet (${currentGemmaModel})`);
    } else if (status === 'unconfigured') {
      dom.healthDot.className = 'health-dot dot-offline';
      dom.healthLabel.textContent = `${modelName}: Unconfigured`;
      if (dom.healthIndicator) dom.healthIndicator.setAttribute('title', 'GEMINI_API_KEY environment variable is not configured');
    } else if (status === 'error') {
      dom.healthDot.className = 'health-dot dot-offline';
      const errorMsg = detail ? `Error (${detail})` : 'Call Failed';
      dom.healthLabel.textContent = `${modelName}: ${errorMsg}`;
      if (dom.healthIndicator) dom.healthIndicator.setAttribute('title', `Last Gemma call failed: ${detail || 'Unknown error'}`);
    }
  }

  async function checkBackendHealth() {
    try {
      const response = await fetch('/api/health');
      if (response.ok) {
        const data = await response.json();
        if (data.model) currentGemmaModel = data.model;
        if (!data.gemini_configured) {
          dom.stateModelUnavailable.style.display = 'flex';
          setGemmaSignal('unconfigured');
        } else {
          // Key is set, but no live inference call has been made yet -> REAL SIGNAL: Unchecked
          setGemmaSignal('unchecked');
        }
      } else {
        setGemmaSignal('error', `HTTP ${response.status}`);
      }
    } catch {
      setGemmaSignal('error', 'API Offline');
    }
  }

  // ============================================================================
  // Unified Diff Parser & Renderer
  // ============================================================================
  function parseAndRenderDiff(rawDiffText) {
    clearElement(dom.diffCodePanel);

    if (!rawDiffText || !rawDiffText.trim()) {
      const emptyNote = createEl('div', 'diff-line', 'No diff content available for this PR.');
      dom.diffCodePanel.appendChild(emptyNote);
      return;
    }

    const lines = rawDiffText.split('\n');
    let lineNumOld = 0;
    let lineNumNew = 0;

    lines.forEach((lineStr, index) => {
      const lineRow = createEl('div', 'diff-line');
      lineRow.id = `diff-line-${index}`;
      lineRow.dataset.lineContent = lineStr;

      let lineType = 'context';
      let oldColText = '';
      let newColText = '';
      let markerText = ' ';

      if (lineStr.startsWith('@@')) {
        lineType = 'hunk';
        markerText = '@';
        // Parse hunk header if possible
        const match = lineStr.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        if (match) {
          lineNumOld = parseInt(match[1], 10) - 1;
          lineNumNew = parseInt(match[2], 10) - 1;
        }
      } else if (lineStr.startsWith('+') && !lineStr.startsWith('+++')) {
        lineType = 'add';
        markerText = '+';
        lineNumNew++;
        newColText = String(lineNumNew);
      } else if (lineStr.startsWith('-') && !lineStr.startsWith('---')) {
        lineType = 'del';
        markerText = '-';
        lineNumOld++;
        oldColText = String(lineNumOld);
      } else if (lineStr.startsWith('---') || lineStr.startsWith('+++')) {
        lineType = 'hunk';
        markerText = lineStr.charAt(0);
      } else {
        lineNumOld++;
        lineNumNew++;
        oldColText = String(lineNumOld);
        newColText = String(lineNumNew);
      }

      lineRow.classList.add(`diff-line-${lineType}`);

      // Line number gutter
      const gutter = createEl('div', 'diff-line-num');
      gutter.textContent = newColText || oldColText || '…';

      // Diff marker (+, -, @)
      const marker = createEl('div', 'diff-marker', markerText);

      // Diff content (strictly textContent!)
      const content = createEl('div', 'diff-content');
      // Strip leading diff marker char for cleanest readability
      const cleanContent = lineStr.length > 0 && ['+', '-', ' '].includes(lineStr[0])
        ? lineStr.substring(1)
        : lineStr;
      content.textContent = cleanContent;

      lineRow.appendChild(gutter);
      lineRow.appendChild(marker);
      lineRow.appendChild(content);

      dom.diffCodePanel.appendChild(lineRow);
    });
  }

  // ============================================================================
  // Recommendation & Priority Visual Mappers
  // ============================================================================
  const REC_DESCRIPTIONS = {
    review: 'Changes appear focused and sound. Recommended for human maintainer code review.',
    needs_work: 'Changes require additional adjustments, tests, or clarifications from the author.',
    low_effort: 'Trivial or mechanical change (e.g. documentation, typo, format fix). Easy to verify.',
    potentially_irrelevant_or_suspicious: 'Suspicious patterns, out-of-scope changes, or automated AI slop signals detected. Review with caution.',
    insufficient_evidence: 'Insufficient factual evidence in diff/description to formulate a confident assessment.'
  };

  const PRIORITY_LABELS = {
    1: '1 / 5 • Trivial / Cosmetic',
    2: '2 / 5 • Minor Enhancement',
    3: '3 / 5 • Moderate Impact',
    4: '4 / 5 • High Priority / Core Path',
    5: '5 / 5 • Critical / Security / Breakage'
  };

  function renderPriorityBar(score) {
    const safeScore = Math.max(1, Math.min(5, parseInt(score, 10) || 1));
    dom.priorityNumericText.textContent = PRIORITY_LABELS[safeScore] || `${safeScore} / 5`;
    dom.priorityProgressBar.setAttribute('aria-valuenow', String(safeScore));

    const dots = dom.priorityProgressBar.querySelectorAll('.priority-dot, .priority-segment');
    dots.forEach((dot, idx) => {
      const dotVal = idx + 1;
      if (dotVal <= safeScore) {
        dot.classList.add('active');
      } else {
        dot.classList.remove('active');
      }
    });
  }

  // ============================================================================
  // Evidence Rail Highlighting Signature Interaction
  // ============================================================================
  // Dossier Tabs Switching
  // ============================================================================
  function switchDossierTab(tabName) {
    const tabBtns = document.querySelectorAll('.dossier-tab');
    tabBtns.forEach(btn => {
      const isActive = btn.dataset.tab === tabName;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    const panels = document.querySelectorAll('.dossier-tab-panel');
    panels.forEach(p => {
      p.style.display = p.id === tabName ? 'block' : 'none';
    });
  }

  // ============================================================================
  // Evidence Rail Highlighting Signature Interaction
  // ============================================================================
  function clearAllHighlights() {
    const highlighted = document.querySelectorAll('.highlight-target, .highlight-target-box');
    highlighted.forEach(el => {
      el.classList.remove('highlight-target', 'highlight-target-box');
    });

    const activeCards = document.querySelectorAll('.active-evidence-card');
    activeCards.forEach(c => c.classList.remove('active-evidence-card'));
  }

  function highlightEvidenceInDesk(item, cardEl) {
    clearAllHighlights();

    if (cardEl) {
      cardEl.classList.add('active-evidence-card');
    }

    const quote = (item.quote || '').trim();
    const source = (item.source || '').toLowerCase();

    // If unverified/quarantined, explain why
    if (!item.verified) {
      dom.dossierSourceTag.textContent = 'QUARANTINE ALERT: Quote unverified in source';
      if (dom.statePartialDataBanner) {
        dom.statePartialDataBanner.style.display = 'flex';
        dom.partialDataTitle.textContent = 'QUARANTINE NOTICE: NOT FOUND IN SOURCE';
        const evidenceList = (state.currentAssessment && state.currentAssessment.evidence) || [];
        const unverifiedCount = evidenceList.filter(e => !e.verified).length || 1;
        const totalCount = evidenceList.length || 1;
        dom.partialDataText.textContent = `${unverifiedCount} of ${totalCount} quotes could not be verified in the source. "${quote}" failed in-code substring verification.`;
        dom.statePartialDataBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      setTimeout(() => {
        dom.dossierSourceTag.textContent = state.isCached ? 'DATA SOURCE: CACHE' : 'DATA SOURCE: GITHUB LIVE';
      }, 5000);
      return;
    }

    let matchFound = false;

    // 1. Search in Diff Lines if source is 'diff' or general
    if (source.includes('diff') || source === 'all') {
      switchDossierTab('tab-diff');
      const diffLines = dom.diffCodePanel.querySelectorAll('.diff-line');
      for (const line of diffLines) {
        const text = line.dataset.lineContent || '';
        if (quote && (text.includes(quote) || quote.includes(text.trim()))) {
          line.classList.add('highlight-target');
          if (!matchFound) {
            line.scrollIntoView({ behavior: 'smooth', block: 'center' });
            matchFound = true;
          }
        }
      }
    }

    // 2. Search in PR Body if source is 'body'
    if (!matchFound && (source.includes('body') || source.includes('description'))) {
      switchDossierTab('tab-overview');
      const bodyText = dom.prBodyContainer.textContent || '';
      if (quote && bodyText.includes(quote)) {
        dom.prBodyContainer.classList.add('highlight-target-box');
        dom.prBodyContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
        matchFound = true;
      }
    }

    // 3. Fallback: Search all visible text in paper panel
    if (!matchFound) {
      switchDossierTab('tab-diff');
      const diffLines = dom.diffCodePanel.querySelectorAll('.diff-line');
      for (const line of diffLines) {
        const text = line.dataset.lineContent || '';
        if (quote && text.toLowerCase().includes(quote.toLowerCase())) {
          line.classList.add('highlight-target');
          line.scrollIntoView({ behavior: 'smooth', block: 'center' });
          matchFound = true;
          break;
        }
      }
    }
  }

  // ============================================================================
  // Assessment Dossier Renderer
  // ============================================================================
  function renderAssessment(assessment) {
    state.currentAssessment = assessment;

    // 1. Recommendation Badge & Verdict Block Background
    const recKey = (assessment.recommendation || 'review').toLowerCase();
    const cardRecommendation = document.getElementById('card-recommendation');
    if (cardRecommendation) {
      cardRecommendation.className = `assessment-card verdict-block verdict-${recKey}`;
    }
    dom.badgeRecommendation.className = `verdict-label rec-${recKey}`;
    dom.badgeRecommendation.textContent = recKey.replace(/_/g, ' ').toUpperCase();
    dom.recExplanationText.textContent = REC_DESCRIPTIONS[recKey] || REC_DESCRIPTIONS.review;

    // 2. Confidence Pill
    const confKey = (assessment.confidence || 'high').toLowerCase();
    dom.badgeConfidence.className = `confidence-pill confidence-${confKey}`;
    dom.badgeConfidence.textContent = `CONFIDENCE: ${confKey.toUpperCase()}`;

    // 3. Priority Bar
    renderPriorityBar(assessment.priority_score || 3);

    // 4. Objective Summary (Safe textContent)
    dom.assessmentSummaryText.textContent = assessment.summary || 'No summary available.';

    // 5. Evidence Rail Items
    clearElement(dom.evidenceItemsContainer);
    const evidenceList = assessment.evidence || [];
    dom.evidenceCountBadge.textContent = `${evidenceList.length} items`;

    evidenceList.forEach((item, index) => {
      const card = createEl('div', 'evidence-item-card');
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.setAttribute('aria-label', `Evidence item ${index + 1}: ${item.claim}`);
      card.setAttribute('aria-expanded', 'false');

      // Header: Source Tag + Verification Status Badge (Text + Stamp) + Expand Toggle
      const header = createEl('div', 'evidence-card-header');
      const srcTag = createEl('span', 'evidence-source-tag', `[${item.source || 'source'}]`);

      const statusBadge = createEl('span', 'verification-status-badge');
      if (item.verified) {
        statusBadge.classList.add('status-verified');
        statusBadge.textContent = 'VERIFIED IN SOURCE';
      } else {
        statusBadge.classList.add('status-quarantined');
        statusBadge.textContent = 'NOT FOUND IN SOURCE';
      }

      const expandToggle = createEl('span', 'evidence-expand-indicator', '+');

      header.appendChild(srcTag);
      header.appendChild(statusBadge);
      header.appendChild(expandToggle);

      // Claim Text (always visible)
      const claim = createEl('p', 'evidence-claim-text', item.claim || 'Unspecified claim');

      // Collapsible details container (collapsed by default)
      const details = createEl('div', 'evidence-card-details');
      details.style.display = 'none';

      // Exact Quote Box
      const quoteBox = createEl('div', 'evidence-quote-snippet', `“${item.quote || ''}”`);

      // Inspection Hint
      const hint = createEl('div', 'evidence-inspect-hint');
      hint.textContent = item.verified
        ? '↘ Locating authentic excerpt in dossier'
        : '⛔ Quarantined: Non-verifiable statement cannot be cited as fact';

      details.appendChild(quoteBox);
      details.appendChild(hint);

      card.appendChild(header);
      card.appendChild(claim);
      card.appendChild(details);

      // Toggle click handler (collapsible on click)
      function toggleEvidence() {
        const isCurrentlyExpanded = details.style.display === 'block';
        if (isCurrentlyExpanded) {
          details.style.display = 'none';
          card.classList.remove('active-evidence-card');
          card.setAttribute('aria-expanded', 'false');
          expandToggle.textContent = '+';
          clearAllHighlights();
        } else {
          details.style.display = 'block';
          card.classList.add('active-evidence-card');
          card.setAttribute('aria-expanded', 'true');
          expandToggle.textContent = '−';
          highlightEvidenceInDesk(item, card);
        }
      }

      card.addEventListener('click', toggleEvidence);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggleEvidence();
        }
      });

      dom.evidenceItemsContainer.appendChild(card);
    });

    // 6. Missing Context
    clearElement(dom.missingContextList);
    const missingItems = assessment.missing_context || [];
    if (missingItems.length === 0) {
      const li = createEl('li', 'missing-context-item', 'None identified. All required context verified.');
      dom.missingContextList.appendChild(li);
    } else {
      missingItems.forEach(itemText => {
        const li = createEl('li', 'missing-context-item');
        const marker = createEl('span', 'missing-item-marker', '•');
        const text = createEl('span', 'missing-item-text', itemText);
        li.appendChild(marker);
        li.appendChild(text);
        dom.missingContextList.appendChild(li);
      });
    }

    // 7. Uncertainty Disclosure
    if (assessment.uncertainty_reason && assessment.uncertainty_reason.trim()) {
      dom.cardUncertainty.style.display = 'block';
      dom.uncertaintyReasonText.textContent = assessment.uncertainty_reason;
    } else {
      dom.cardUncertainty.style.display = 'none';
    }

    // 8. Maintainer Response Draft (Safe textarea value)
    dom.replyDraftTextarea.value = assessment.suggested_response || '';
  }

  // ============================================================================
  // Complete Dossier Loader
  // ============================================================================
  function loadDossierIntoDesk(dossierData) {
    state.currentPR = dossierData.pr;
    state.currentAssessment = dossierData.assessment || dossierData.data;
    state.isCached = Boolean(dossierData.cache_hit);

    showViewState('content');

    // 1. Update Mode Indicator Badges
    if (dom.modeIndicator && dom.modeIndicatorText) {
      dom.modeIndicator.style.display = 'inline-flex';
      if (dossierData.cache_hit) {
        dom.modeIndicator.className = 'status-badge badge-cached';
        dom.modeIndicatorText.textContent = 'CACHED';
        dom.dossierTypeBadge.textContent = 'CACHED PR DOSSIER';
        dom.dossierSourceTag.textContent = `DATA SOURCE: CACHE (${dossierData.cache_label || 'cached'})`;
        dom.footerDataSource.textContent = (dossierData.metadata && dossierData.metadata.dataSource) || 'Local Cache';
      } else {
        dom.modeIndicator.className = 'status-badge badge-live';
        dom.modeIndicatorText.textContent = 'LIVE INVESTIGATION';
        dom.dossierTypeBadge.textContent = 'LIVE PR DOSSIER';
        dom.dossierSourceTag.textContent = 'DATA SOURCE: GITHUB REST API';
        dom.footerDataSource.textContent = (dossierData.metadata && dossierData.metadata.dataSource) || 'GitHub REST API (Live)';
      }
    }

    // 2. Toolbar & Metadata
    const pr = dossierData.pr || {};
    dom.dossierSlug.textContent = `${pr.owner}/${pr.repo}#${pr.pull_number}`;
    dom.branchInfo.textContent = `${pr.base_branch || 'main'} ← ${pr.head_branch || 'patch'}`;
    dom.viewOnGithubLink.href = pr.html_url || '#';

    // 3. Metadata Card (Pure textContent)
    dom.prNumberBadge.textContent = `#${pr.pull_number}`;
    dom.prHeadlineText.textContent = pr.title || 'Untitled Pull Request';
    dom.prAuthorVal.textContent = `@${pr.author || 'author'}`;
    if (dom.prAssocVal) {
      dom.prAssocVal.textContent = (pr.author_association || 'CONTRIBUTOR').replace(/_/g, ' ');
    }
    const rawState = (pr.state || 'open').toLowerCase();
    dom.prStateVal.textContent = rawState.toUpperCase();
    dom.prStateVal.className = `meta-value state-tag state-${rawState}`;

    clearElement(dom.prDeltaVal);
    const addSpan = createEl('span', 'stat-add', `+${pr.additions || 0}`);
    const delSpan = createEl('span', 'stat-del', `-${pr.deletions || 0}`);
    const filesSpan = createEl('span', null, ` (${pr.changed_files || 1} files)`);
    dom.prDeltaVal.appendChild(addSpan);
    dom.prDeltaVal.appendChild(document.createTextNode(' / '));
    dom.prDeltaVal.appendChild(delSpan);
    dom.prDeltaVal.appendChild(filesSpan);

    // 4. PR Body Container
    clearElement(dom.prBodyContainer);
    dom.prBodyContainer.textContent = pr.body || 'No description provided by author.';

    // 5. Changed Files List
    clearElement(dom.changedFilesList);
    const files = dossierData.files || [];
    dom.fileCountBadge.textContent = `${files.length} file${files.length === 1 ? '' : 's'} changed`;
    const tabFileBadge = document.getElementById('tab-file-count-badge');
    if (tabFileBadge) {
      tabFileBadge.textContent = String(files.length);
    }
    if (files.length === 0) {
      const item = createEl('li', 'file-item');
      item.appendChild(createEl('span', 'file-path', 'No files modified'));
      dom.changedFilesList.appendChild(item);
    } else {
      files.forEach(f => {
        const item = createEl('li', 'file-item');
        const path = createEl('span', 'file-path', f.path || f.filename);
        const stats = createEl('span', 'file-stats');
        const aSpan = createEl('span', 'stat-add', `+${f.additions || 0}`);
        const dSpan = createEl('span', 'stat-del', `-${f.deletions || 0}`);
        stats.appendChild(aSpan);
        stats.appendChild(document.createTextNode(' '));
        stats.appendChild(dSpan);
        item.appendChild(path);
        item.appendChild(stats);
        dom.changedFilesList.appendChild(item);
      });
    }

    // 6. Diff Code Panel
    const rawDiff = dossierData.diff || '';
    dom.diffFilePathText.textContent = (files[0] && (files[0].path || files[0].filename)) || 'Diff excerpt';
    parseAndRenderDiff(rawDiff);

    // 7. Assessment Section
    renderAssessment(dossierData.assessment || dossierData.data || {});

    // 8. Partial-Data & Quarantine State Checking (Real Counts)
    const evidenceList = (dossierData.assessment && dossierData.assessment.evidence) || [];
    const unverifiedQuotes = evidenceList.filter(e => !e.verified).length;
    const totalQuotes = evidenceList.length;

    const isTruncated = Boolean(
      dossierData.diff_truncated ||
      (dossierData.diff_summary && dossierData.diff_summary.truncated) ||
      (dossierData.diff && dossierData.diff.includes('... [Diff truncated'))
    );

    if (unverifiedQuotes > 0) {
      dom.diffTruncationBadge.style.display = isTruncated ? 'inline-block' : 'none';
      dom.statePartialDataBanner.style.display = 'flex';
      dom.partialDataTitle.textContent = 'Evidence Quarantine Notice';
      dom.partialDataText.textContent = `${unverifiedQuotes} of ${totalQuotes} quotes could not be verified in the source.`;
    } else if (isTruncated || dossierData.isPartial) {
      dom.diffTruncationBadge.style.display = 'inline-block';
      dom.statePartialDataBanner.style.display = 'flex';
      dom.partialDataTitle.textContent = 'Partial Data Detected: Unified Diff Truncated';
      dom.partialDataText.textContent = 'The pull request diff exceeded the safe line limit (1,500 lines) and was truncated. Code quote verification is strictly scoped to the retrieved text.';
    } else {
      dom.diffTruncationBadge.style.display = 'none';
      dom.statePartialDataBanner.style.display = 'none';
    }

    // 9. Footer Info & Re-run Live
    if (dossierData.metadata) {
      if (dossierData.metadata.auditedAt) dom.footerTimestamp.textContent = dossierData.metadata.auditedAt;
      if (dossierData.metadata.assessorModel) dom.footerModelName.textContent = dossierData.metadata.assessorModel;
      if (dossierData.metadata.dataSource) dom.footerDataSource.textContent = dossierData.metadata.dataSource;
    } else if (dossierData.cached_on) {
      dom.footerTimestamp.textContent = dossierData.cached_on;
      dom.footerDataSource.textContent = `Cache (${dossierData.cache_label || 'cached'})`;
    }

    if (dom.btnRerunLive) {
      dom.btnRerunLive.style.display = dossierData.cache_hit ? 'inline-block' : 'none';
    }

    // Footnote "Substrings Verified" must appear ONLY when verification ran on the displayed result
    const assessmentObj = dossierData.assessment || dossierData.data;
    const verificationRan = Boolean(
      assessmentObj &&
      Array.isArray(assessmentObj.evidence) &&
      assessmentObj.evidence.length > 0 &&
      assessmentObj.evidence.some(e => typeof e.verified === 'boolean')
    );
    if (dom.footerVerifiedBadge) {
      dom.footerVerifiedBadge.style.display = verificationRan ? 'inline' : 'none';
    }

    // 10. Show Content
    state.currentDossier = dossierData;
    switchDossierTab('tab-overview');
    showViewState('content');
  }

  // ============================================================================
  // Typed Error Presentation
  // ============================================================================
  function sanitizeErrorDetails(details) {
    if (!details) return '';
    const str = String(details).trim();
    if (str.startsWith('{') || str.includes('"error":') || str.includes('"code":')) {
      try {
        const parsed = JSON.parse(str);
        if (parsed.error && parsed.error.message) return parsed.error.message;
        if (parsed.message) return parsed.message;
      } catch {
        const match = str.match(/"message"\s*:\s*"([^"]+)"/);
        if (match) return match[1];
      }
      return 'The request was throttled or rejected by the service provider.';
    }
    return str;
  }

  function showError(errorType, message, details) {
    showViewState('error');
    if (dom.errorTitle) {
      if (errorType === 'invalid_repo' || errorType === 'invalid_input') {
        dom.errorTitle.textContent = 'Invalid Repository or PR Input';
      } else if (errorType === 'not_found') {
        dom.errorTitle.textContent = 'Repository or PR Not Found';
      } else if (errorType === 'rate_limit') {
        dom.errorTitle.textContent = 'Rate Limit Exceeded';
      } else if (errorType === 'no_prs') {
        dom.errorTitle.textContent = 'No Open Pull Requests';
      } else if (errorType === 'network_error') {
        dom.errorTitle.textContent = 'GitHub API Connection Error';
      } else if (errorType === 'model_unavailable') {
        dom.errorTitle.textContent = 'Gemma 4 Service Unavailable';
      } else if (errorType === 'invalid_model_output') {
        dom.errorTitle.textContent = 'Invalid Model Response';
      } else {
        dom.errorTitle.textContent = 'Investigation Error';
      }
    }

    if (dom.errorMessageText) {
      dom.errorMessageText.textContent = message || 'An error occurred during triage processing.';
    }

    if (details && dom.errorDetailsContainer && dom.errorDetailsCode) {
      dom.errorDetailsContainer.style.display = 'block';
      dom.errorDetailsCode.textContent = sanitizeErrorDetails(details);
    } else if (dom.errorDetailsContainer) {
      dom.errorDetailsContainer.style.display = 'none';
    }
  }

  // ============================================================================
  // Input Routing & Pull Request Queue Loading (POST /api/prs)
  // ============================================================================
  function isPRReference(inputStr) {
    const raw = (inputStr || '').trim();
    return raw.includes('#') || raw.includes('/pull/');
  }

  async function handleInputSubmit(rawInput) {
    const cleanInput = (rawInput || '').trim();
    if (!cleanInput) {
      showError('invalid_input', 'Please enter a GitHub repository (e.g. pallets/flask) or a PR URL.');
      dom.prUrlInput.focus();
      return;
    }

    if (isPRReference(cleanInput)) {
      await analyzePullRequest(cleanInput);
    } else {
      await loadRepoPullRequests(cleanInput);
    }
  }

  async function loadRepoPullRequests(repoInput) {
    const clean = repoInput.trim();
    showViewState('loading');

    const steps = [
      document.getElementById('load-step-1'),
      document.getElementById('load-step-2'),
      document.getElementById('load-step-3'),
      document.getElementById('load-step-4')
    ];
    if (steps[0]) {
      steps[0].className = 'timeline-step step-active';
      const textSpan = steps[0].querySelector('.step-text');
      if (textSpan) textSpan.textContent = `Fetching PR list for ${clean}…`;
    }
    for (let i = 1; i < steps.length; i++) {
      if (steps[i]) steps[i].className = 'timeline-step';
    }

    try {
      const response = await fetch('/api/prs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: clean })
      });

      const resData = await response.json();
      if (!response.ok || resData.status === 'error') {
        const errType = resData.error_type || 'server_error';
        const errMsg = resData.error || `HTTP ${response.status}: Failed to fetch repository PRs`;
        const details = resData.details || errMsg;
        showError(errType, errMsg, details);
        return;
      }

      const prList = resData.prs || [];
      state.currentRepo = resData.repo;

      if (prList.length === 0) {
        showViewState('empty');
        if (dom.queueCount) dom.queueCount.textContent = '0 items';
        if (dom.queueList) {
          clearElement(dom.queueList);
          const emptyItem = createEl('li', 'queue-empty-item', `No open PRs found for ${resData.repo}`);
          dom.queueList.appendChild(emptyItem);
        }
        showError('no_prs', `No open pull requests found for '${resData.repo}'.`, 'GitHub reports 0 open pull requests.');
        return;
      }

      // Render Queue List (Limit 10)
      renderPRQueue(resData.repo, prList);

      // Set desk view to empty state with instructions
      showViewState('empty');
      const emptyTitle = dom.stateEmpty.querySelector('.empty-title');
      const emptyDesc = dom.stateEmpty.querySelector('.empty-desc');
      if (emptyTitle) emptyTitle.textContent = `${resData.repo} (${prList.length} open PR${prList.length === 1 ? '' : 's'})`;
      if (emptyDesc) emptyDesc.textContent = 'Select a pull request from the queue on the left to analyze evidence, inspect unified diffs, and verify quotes with Gemma 4.';

    } catch (err) {
      showError('network_error', 'Failed to connect to backend server.', String(err.message || err));
    }
  }

  function renderPRQueue(repoSlug, prList) {
    if (!dom.queueList || !dom.queueCount) return;
    clearElement(dom.queueList);
    dom.queueCount.textContent = `${prList.length} item${prList.length === 1 ? '' : 's'}`;

    prList.forEach(pr => {
      const li = createEl('li', 'queue-item');
      li.id = `queue-pr-${pr.number}`;
      li.tabIndex = 0;
      li.setAttribute('role', 'option');

      const header = createEl('div', 'queue-item-header');
      const prSlugSpan = createEl('span', 'queue-item-repo', `${repoSlug}#${pr.number}`);
      const stateBadge = createEl('span', ['queue-item-badge', 'badge-live'], 'OPEN');
      header.appendChild(prSlugSpan);
      header.appendChild(stateBadge);

      const title = createEl('div', 'queue-item-title', pr.title || 'Untitled Pull Request');

      const meta = createEl('div', 'queue-item-meta');
      const authorText = pr.author ? `@${pr.author}` : '';
      const updatedText = pr.updated_at ? pr.updated_at.substring(0, 10) : '';
      meta.textContent = [authorText, updatedText].filter(Boolean).join(' • ');

      li.appendChild(header);
      li.appendChild(title);
      li.appendChild(meta);

      // On Click -> Calls POST /api/analyze for that single PR!
      li.addEventListener('click', () => {
        if (state.isAnalyzing) {
          console.warn('Analysis already in progress. Ignoring duplicate click.');
          return;
        }
        const allItems = dom.queueList.querySelectorAll('.queue-item');
        allItems.forEach(item => item.classList.remove('active'));
        li.classList.add('active');

        analyzePullRequest({
          repo: repoSlug,
          number: pr.number,
          pr_url: pr.html_url
        });
      });

      li.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          li.click();
        }
      });

      dom.queueList.appendChild(li);
    });
  }

  // ============================================================================
  // Single Pull Request Assessment Orchestration (POST /api/analyze)
  // ============================================================================
  async function analyzePullRequest(target, options = {}) {
    if (state.isAnalyzing) {
      console.warn('Analysis in progress. Blocking concurrent/duplicate request.');
      return;
    }
    state.isAnalyzing = true;
    if (dom.btnAnalyze) dom.btnAnalyze.disabled = true;
    if (dom.btnRerunLive) dom.btnRerunLive.disabled = true;
    if (dom.btnErrorRetry) dom.btnErrorRetry.disabled = true;

    state.lastAnalyzeTarget = target;
    const isAutoRetry = Boolean(options.isAutoRetry);

    let payload = {};

    if (typeof target === 'string') {
      const cleanInput = target.trim();
      const refMatch = cleanInput.match(/^([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+)#(\d+)$/);
      const urlMatch = cleanInput.match(/^https?:\/\/github\.com\/([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+)\/pull\/(\d+)/);
      if (refMatch) {
        payload = {
          owner: refMatch[1],
          repo: refMatch[2],
          pull_number: parseInt(refMatch[3], 10),
          pr_url: `https://github.com/${refMatch[1]}/${refMatch[2]}/pull/${refMatch[3]}`
        };
      } else if (urlMatch) {
        payload = {
          owner: urlMatch[1],
          repo: urlMatch[2],
          pull_number: parseInt(urlMatch[3], 10),
          pr_url: cleanInput
        };
      } else {
        payload = { pr_url: cleanInput };
      }
    } else if (typeof target === 'object' && target !== null) {
      payload = Object.assign({}, target);
    }

    if (options.force_live) {
      payload.force_live = true;
    }

    // Check if a cached dossier exists for this PR
    const currentPRNum = state.currentDossier && (state.currentDossier.pull_number || (state.currentDossier.pr && state.currentDossier.pr.number));
    const targetPRNum = payload.pull_number || payload.number;
    const hasCachedDossier = Boolean(
      state.currentDossier &&
      (!targetPRNum || targetPRNum === currentPRNum)
    );

    // Hide any previous live failure banner on new attempt
    if (dom.stateLiveFailureBanner) dom.stateLiveFailureBanner.style.display = 'none';

    showViewState('loading');

    const steps = [
      document.getElementById('load-step-1'),
      document.getElementById('load-step-2'),
      document.getElementById('load-step-3'),
      document.getElementById('load-step-4')
    ];

    const stepLabels = [
      'Fetching PR facts',
      'Reading changed files',
      'Gemma assessing',
      'Verifying quotes'
    ];
    steps.forEach((s, i) => {
      if (s) {
        s.className = 'timeline-step';
        const txt = s.querySelector('.step-text');
        if (txt) txt.textContent = stepLabels[i];
      }
    });

    const loadingTitle = dom.stateLoading.querySelector('.loading-title');
    const loadingSubtext = dom.stateLoading.querySelector('.loading-subtext');
    if (loadingTitle) loadingTitle.textContent = 'Analyzing Pull Request…';
    if (loadingSubtext) loadingSubtext.textContent = 'Waiting for real backend response. Zero contributor profiling.';

    if (steps[0]) steps[0].className = 'timeline-step step-active';

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      let resData = null;
      try {
        resData = await response.json();
      } catch {
        resData = {
          status: 'error',
          error_type: 'server_error',
          error: `HTTP ${response.status}: Failed to parse server response`
        };
      }

      // Check HTTP 429 or rate_limit
      if (response.status === 429 || resData.error_type === 'rate_limit') {
        const delay = parseInt(resData.retry_delay, 10) || 15;
        if (!isAutoRetry) {
          // Auto-retry ONCE with countdown
          let secondsLeft = delay;
          if (loadingTitle) {
            loadingTitle.textContent = `Rate limited by the free Gemini tier. Retrying in ${secondsLeft}s`;
          }
          if (loadingSubtext) {
            loadingSubtext.textContent = 'Free Gemini tier quota cooling down. Automatic retry will fire once the window resets.';
          }

          if (state.loadingTimer) {
            clearInterval(state.loadingTimer);
          }

          state.loadingTimer = setInterval(() => {
            secondsLeft -= 1;
            if (secondsLeft > 0) {
              if (loadingTitle) {
                loadingTitle.textContent = `Rate limited by the free Gemini tier. Retrying in ${secondsLeft}s`;
              }
            } else {
              clearInterval(state.loadingTimer);
              state.loadingTimer = null;
              state.isAnalyzing = false; // Release lock for auto-retry invocation
              analyzePullRequest(target, { isAutoRetry: true, force_live: Boolean(payload.force_live) });
            }
          }, 1000);
          return;
        }

        // Already retried once, still rate-limited!
        if (hasCachedDossier) {
          loadDossierIntoDesk(state.currentDossier);
          if (dom.stateLiveFailureBanner) {
            dom.stateLiveFailureBanner.style.display = 'flex';
            const cacheTime = state.currentDossier.cached_on || state.currentDossier.cached_at || 'earlier';
            dom.liveFailureText.textContent = `Live run failed (Rate limited by the free Gemini tier). Showing cached result from ${cacheTime}.`;
          }
          return;
        }

        showError(
          'rate_limit',
          'Rate limited by the free Gemini tier. Please wait a moment and click Retry Request.',
          'The free Gemini tier rate limit was reached. You can manually retry using the button below.'
        );
        setGemmaSignal('error', 'Rate limited');
        return;
      }

      if (!response.ok || resData.status === 'error') {
        const errType = resData.error_type || 'server_error';
        const errMsg = resData.error || `HTTP ${response.status}: Analysis failed`;
        const details = resData.details || errMsg;

        if (hasCachedDossier && (payload.force_live || options.force_live)) {
          loadDossierIntoDesk(state.currentDossier);
          if (dom.stateLiveFailureBanner) {
            dom.stateLiveFailureBanner.style.display = 'flex';
            const cacheTime = state.currentDossier.cached_on || state.currentDossier.cached_at || 'earlier';
            dom.liveFailureText.textContent = `Live run failed (${errMsg}). Showing cached result from ${cacheTime}.`;
          }
          return;
        }

        showError(errType, errMsg, details);
        setGemmaSignal('error', errMsg.substring(0, 20));
        return;
      }

      // Mark all completed stages
      steps.forEach(s => {
        if (s) s.className = 'timeline-step step-done';
      });

      if (resData.model) currentGemmaModel = resData.model;
      setGemmaSignal('online');

      // Update PR queue active item badge if in queue
      const prNumber = resData.pull_number || (resData.pr && resData.pr.number);
      if (prNumber) {
        const qItem = document.getElementById(`queue-pr-${prNumber}`);
        if (qItem) {
          const badge = qItem.querySelector('.queue-item-badge');
          if (badge) {
            badge.className = `queue-item-badge ${resData.cache_hit ? 'badge-cached' : 'badge-live'}`;
            badge.textContent = resData.cache_hit ? 'CACHED' : 'LIVE';
          }
          const meta = qItem.querySelector('.queue-item-meta');
          const assessmentObj = resData.assessment || resData.data || {};
          const verifiedFacts = (assessmentObj.evidence || []).filter(e => e.verified).length;
          if (meta) {
            meta.textContent = `@${(resData.pr && resData.pr.author) || 'author'} • ${verifiedFacts} verified facts`;
          }
        } else {
          // Direct PR URL analyzed; prepend to queue
          const prSlug = resData.repo ? `${resData.repo}#${prNumber}` : `#${prNumber}`;
          const li = createEl('li', ['queue-item', 'active']);
          li.id = `queue-pr-${prNumber}`;
          li.tabIndex = 0;
          const header = createEl('div', 'queue-item-header');
          header.appendChild(createEl('span', 'queue-item-repo', prSlug));
          header.appendChild(createEl('span', ['queue-item-badge', resData.cache_hit ? 'badge-cached' : 'badge-live'], resData.cache_hit ? 'CACHED' : 'LIVE'));
          const title = createEl('div', 'queue-item-title', (resData.pr && resData.pr.title) || 'Pull Request');
          const meta = createEl('div', 'queue-item-meta');
          const assessmentObj = resData.assessment || resData.data || {};
          const verifiedFacts = (assessmentObj.evidence || []).filter(e => e.verified).length;
          meta.textContent = `@${(resData.pr && resData.pr.author) || 'author'} • ${verifiedFacts} verified facts`;
          li.appendChild(header);
          li.appendChild(title);
          li.appendChild(meta);
          li.addEventListener('click', () => {
            if (state.isAnalyzing) return;
            loadDossierIntoDesk(resData);
          });
          if (dom.queueList) {
            const emptyItems = dom.queueList.querySelectorAll('.queue-empty-item');
            emptyItems.forEach(el => el.remove());
            dom.queueList.prepend(li);
            if (dom.queueCount) {
              const count = dom.queueList.querySelectorAll('.queue-item').length;
              dom.queueCount.textContent = `${count} item${count === 1 ? '' : 's'}`;
            }
          }
        }
      }

      loadDossierIntoDesk(resData);

    } catch (err) {
      if (hasCachedDossier && (payload.force_live || options.force_live)) {
        loadDossierIntoDesk(state.currentDossier);
        if (dom.stateLiveFailureBanner) {
          dom.stateLiveFailureBanner.style.display = 'flex';
          const cacheTime = state.currentDossier.cached_on || state.currentDossier.cached_at || 'earlier';
          dom.liveFailureText.textContent = `Live run failed (${String(err.message || err)}). Showing cached result from ${cacheTime}.`;
        }
      } else {
        showError('network_error', 'Connection to analysis endpoint failed.', String(err.message || err));
        setGemmaSignal('error', 'Network error');
      }
    } finally {
      if (!state.loadingTimer) {
        state.isAnalyzing = false;
        if (dom.btnAnalyze) dom.btnAnalyze.disabled = false;
        if (dom.btnRerunLive) dom.btnRerunLive.disabled = false;
        if (dom.btnErrorRetry) dom.btnErrorRetry.disabled = false;
      }
    }
  }

  // ============================================================================
  // Copy to Clipboard (Human-in-the-Loop Supremacy)
  // ============================================================================
  function copyResponseDraft() {
    const textToCopy = dom.replyDraftTextarea.value || '';
    if (!textToCopy) {
      alert('Draft is empty.');
      return;
    }

    navigator.clipboard.writeText(textToCopy).then(() => {
      dom.btnCopyDraftText.textContent = 'Copied!';
      dom.copyToast.style.display = 'flex';
      setTimeout(() => {
        dom.btnCopyDraftText.textContent = 'Copy Response Draft';
        dom.copyToast.style.display = 'none';
      }, 3000);
    }).catch(() => {
      // Fallback for older browsers
      dom.replyDraftTextarea.select();
      document.execCommand('copy');
      dom.btnCopyDraftText.textContent = 'Copied!';
      setTimeout(() => {
        dom.btnCopyDraftText.textContent = 'Copy Response Draft';
      }, 3000);
    });
  }

  function resetResponseDraft() {
    if (state.currentAssessment && state.currentAssessment.suggested_response) {
      dom.replyDraftTextarea.value = state.currentAssessment.suggested_response;
    }
  }

  // ============================================================================
  // Event Bindings & Initial Launch
  // ============================================================================
  function init() {
    // View switching helper
    function switchAppView(viewName) {
      const landing = document.getElementById('view-landing');
      const workspace = document.getElementById('view-workspace');
      if (landing && workspace) {
        landing.style.display = viewName === 'landing' ? 'block' : 'none';
        workspace.style.display = viewName === 'workspace' ? 'flex' : 'none';
      }
    }

    // Landing view navigation buttons
    const btnLandingOpen = document.getElementById('btn-landing-open');
    const btnLandingOpenNav = document.getElementById('btn-landing-open-nav');
    if (btnLandingOpen) btnLandingOpen.addEventListener('click', () => switchAppView('workspace'));
    if (btnLandingOpenNav) btnLandingOpenNav.addEventListener('click', () => switchAppView('workspace'));

    // Workspace Home link
    const btnNavHome = document.getElementById('btn-nav-home');
    if (btnNavHome) btnNavHome.addEventListener('click', () => switchAppView('landing'));

    // Dossier Tab switching event listeners
    const tabBtns = document.querySelectorAll('.dossier-tab');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const tab = e.currentTarget.dataset.tab;
        if (tab) switchDossierTab(tab);
      });
    });

    // Form submission & buttons
    if (dom.btnAnalyze) {
      dom.btnAnalyze.addEventListener('click', () => {
        if (state.isAnalyzing) return;
        handleInputSubmit(dom.prUrlInput.value);
      });
    }

    if (dom.prUrlInput) {
      dom.prUrlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          if (state.isAnalyzing) return;
          handleInputSubmit(dom.prUrlInput.value);
        }
      });
    }

    if (dom.btnErrorRetry) {
      dom.btnErrorRetry.addEventListener('click', () => {
        if (state.isAnalyzing) return;
        if (state.lastAnalyzeTarget) {
          analyzePullRequest(state.lastAnalyzeTarget);
        } else {
          handleInputSubmit(dom.prUrlInput.value);
        }
      });
    }

    if (dom.btnRerunLive) {
      dom.btnRerunLive.addEventListener('click', () => {
        if (state.isAnalyzing) return;
        if (state.currentPR) {
          const pr = state.currentPR;
          const repo = (pr.owner && pr.repo) ? `${pr.owner}/${pr.repo}` : state.currentRepo;
          const number = pr.pull_number || pr.number;
          if (repo && number) {
            analyzePullRequest({
              repo: repo,
              number: number,
              force_live: true
            }, { force_live: true });
          }
        }
      });
    }

    if (dom.btnDismissLiveFailure) {
      dom.btnDismissLiveFailure.addEventListener('click', () => {
        if (dom.stateLiveFailureBanner) {
          dom.stateLiveFailureBanner.style.display = 'none';
        }
      });
    }

    dom.btnDismissAlert.addEventListener('click', () => {
      dom.stateModelUnavailable.style.display = 'none';
    });

    dom.btnCopyDraft.addEventListener('click', copyResponseDraft);
    dom.btnResetDraft.addEventListener('click', resetResponseDraft);

    // Expand / collapse suggested-reply draft
    const btnToggleExpand = document.getElementById('btn-toggle-expand-draft');
    const cardReply = document.getElementById('card-reply-draft');
    if (btnToggleExpand && cardReply) {
      btnToggleExpand.addEventListener('click', () => {
        const isExpanded = cardReply.classList.toggle('is-expanded');
        btnToggleExpand.textContent = isExpanded ? 'Collapse' : 'Expand';
        if (isExpanded) {
          dom.replyDraftTextarea.setAttribute('rows', '6');
        } else {
          dom.replyDraftTextarea.setAttribute('rows', '3');
        }
      });
    }

    // Escape clears evidence highlight
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        clearAllHighlights();
      }
    });

    // Check backend health
    checkBackendHealth();

    // Default state: empty state ("Enter a public repository")
    showViewState('empty');
    if (dom.queueCount) dom.queueCount.textContent = '0 items';
    if (dom.queueList) {
      clearElement(dom.queueList);
      const emptyItem = createEl('li', 'queue-empty-item', 'Enter a repository to load PRs');
      dom.queueList.appendChild(emptyItem);
    }

    // Default view on first load: Landing view
    switchAppView('landing');
  }

  // Execute on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
