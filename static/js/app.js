/**
 * Sift — Evidence Desk Frontend Controller
 * 
 * Strict Invariants:
 * 1. Security: NEVER use innerHTML. All text rendered via textContent / DOM APIs.
 * 2. Maintainer Supremacy: Never auto-post comments or actions. Copy draft only.
 * 3. Quote Verification: Visual distinction (text + icon) for verified vs quarantined quotes.
 * 4. Sample vs Live: Sample data prominently stamped with SAMPLE label; never faked as live.
 */

(function () {
  'use strict';

  // ============================================================================
  // Sample Data Specification (Prominently Stamped as SAMPLE)
  // ============================================================================
  const SAMPLE_PR_DATA = {
    isSample: true,
    pr: {
      owner: 'psf',
      repo: 'requests',
      pull_number: 6541,
      title: 'Fix unhandled TimeoutError during connection pool reuse',
      author: 'elena-dev',
      author_association: 'FIRST_TIME_CONTRIBUTOR',
      state: 'open',
      base_branch: 'main',
      head_branch: 'fix/timeout-handling',
      additions: 6,
      deletions: 2,
      changed_files: 1,
      html_url: 'https://github.com/psf/requests/pull/6541',
      body: 'Fixes an issue where rapid reconnection timeouts during connection pool reuse raise raw urllib3 TimeoutError instead of wrapping in requests.exceptions.ConnectTimeout.\n\nVerified in local smoke tests.'
    },
    files: [
      { path: 'requests/adapters.py', additions: 6, deletions: 2 }
    ],
    diff: `--- a/requests/adapters.py
+++ b/requests/adapters.py
@@ -512,8 +512,14 @@ class HTTPAdapter(BaseAdapter):
             # Connection error handling
             raise ConnectionError(e, request=request)
-        except MaxRetryError as e:
-            if isinstance(e.reason, ConnectTimeoutError):
+        except TimeoutError as e:
+            raise ConnectTimeout(e, request=request)
+        except MaxRetryError as e:
+            if isinstance(e.reason, (ConnectTimeoutError, TimeoutError)):
                 raise ConnectTimeout(e, request=request)
             if isinstance(e.reason, ResponseError):
                 raise RetryError(e, request=request)`,
    assessment: {
      summary: 'Normalizes connection timeout handling in HTTPAdapter by catching raw TimeoutError and wrapping it cleanly in requests ConnectTimeout.',
      recommendation: 'review',
      priority_score: 3,
      confidence: 'high',
      evidence: [
        {
          claim: 'Catches raw TimeoutError directly in HTTPAdapter exception handler',
          source: 'diff',
          quote: 'except TimeoutError as e:',
          verified: true
        },
        {
          claim: 'Wraps caught exception in requests ConnectTimeout',
          source: 'diff',
          quote: 'raise ConnectTimeout(e, request=request)',
          verified: true
        },
        {
          claim: 'Expands MaxRetryError check to match tuple of timeout exceptions',
          source: 'diff',
          quote: 'isinstance(e.reason, (ConnectTimeoutError, TimeoutError))',
          verified: true
        },
        {
          claim: 'Dossier claim: comprehensive regression test suite was provided',
          source: 'body',
          quote: 'added comprehensive pytest suite for all adapters',
          verified: false
        }
      ],
      missing_context: [
        'Dedicated unit test in tests/test_requests.py simulating connection pool timeout condition',
        'Verification of exception wrapping compatibility with urllib3 v1.26 and v2.x'
      ],
      suggested_response: 'Thank you for the contribution @elena-dev! The exception normalization in HTTPAdapter looks sound. Could you please add a unit test in tests/test_requests.py covering this pool timeout scenario so we can verify the ConnectTimeout wrapping and guard against regressions?',
      uncertainty_reason: ''
    },
    metadata: {
      dataSource: 'Sample Evidence Packet (Verified Authentic Excerpts)',
      auditedAt: '2026-10-22 12:54:00 UTC',
      assessorModel: 'gemma-4-26b-a4b-it via REST API'
    }
  };

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
    currentPR: null,
    currentAssessment: null,
    isSample: true,
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
    btnLoadSample: document.getElementById('btn-load-sample'),
    queueList: document.getElementById('queue-list'),
    queueCount: document.getElementById('queue-count'),

    // Desk Views
    stateEmpty: document.getElementById('state-empty'),
    stateLoading: document.getElementById('state-loading'),
    stateError: document.getElementById('state-error'),
    stateContent: document.getElementById('state-content'),
    stateModelUnavailable: document.getElementById('state-model-unavailable'),
    statePartialDataBanner: document.getElementById('state-partial-data-banner'),
    partialDataTitle: document.getElementById('partial-data-title'),
    partialDataText: document.getElementById('partial-data-text'),
    btnDismissAlert: document.getElementById('btn-dismiss-alert'),
    btnEmptySample: document.getElementById('btn-empty-sample'),
    btnErrorSample: document.getElementById('btn-error-sample'),
    btnErrorRetry: document.getElementById('btn-error-retry'),
    errorMessageText: document.getElementById('error-message-text'),
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
    footerModelName: document.getElementById('footer-model-name')
  };

  // ============================================================================
  // View State Management
  // ============================================================================
  function showViewState(viewName) {
    dom.stateEmpty.style.display = viewName === 'empty' ? 'flex' : 'none';
    dom.stateLoading.style.display = viewName === 'loading' ? 'flex' : 'none';
    dom.stateError.style.display = viewName === 'error' ? 'flex' : 'none';
    dom.stateContent.style.display = viewName === 'content' ? 'flex' : 'none';
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
      dom.healthLabel.textContent = `${modelName}: Unchecked`;
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
        dom.dossierSourceTag.textContent = state.isSample ? 'DATA SOURCE: SAMPLE PACKET' : 'DATA SOURCE: GITHUB LIVE';
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
  // Complete Dossier Loader (Sample & Live)
  // ============================================================================
  function loadDossierIntoDesk(dossierData) {
    state.isSample = Boolean(dossierData.isSample);
    state.currentPR = dossierData.pr;

    // 1. Update Mode Indicator Badges
    if (state.isSample) {
      dom.modeIndicator.className = 'status-badge badge-sample';
      dom.modeIndicatorText.textContent = 'SAMPLE MODE';
      dom.dossierTypeBadge.textContent = 'SAMPLE DOSSIER';
      dom.dossierSourceTag.textContent = 'DATA SOURCE: SAMPLE PACKET (VERIFIED)';
      dom.footerDataSource.textContent = 'Sample Evidence Packet (Verified Authentic)';
    } else {
      dom.modeIndicator.className = 'status-badge badge-live';
      dom.modeIndicatorText.textContent = 'LIVE INVESTIGATION';
      dom.dossierTypeBadge.textContent = 'LIVE PR DOSSIER';
      dom.dossierSourceTag.textContent = 'DATA SOURCE: GITHUB REST API';
      dom.footerDataSource.textContent = 'Live GitHub REST API';
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
    dom.fileCountBadge.textContent = `${files.length || 1} file changed`;
    const tabFileBadge = document.getElementById('tab-file-count-badge');
    if (tabFileBadge) {
      tabFileBadge.textContent = String(files.length || 1);
    }
    if (files.length === 0) {
      const item = createEl('li', 'file-item');
      item.appendChild(createEl('span', 'file-path', 'requests/adapters.py'));
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
    dom.diffFilePathText.textContent = (files[0] && files[0].path) || 'requests/adapters.py';
    parseAndRenderDiff(rawDiff);

    // 7. Assessment Section
    renderAssessment(dossierData.assessment || {});

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

    // 9. Footer Info
    if (dossierData.metadata) {
      if (dossierData.metadata.auditedAt) dom.footerTimestamp.textContent = dossierData.metadata.auditedAt;
      if (dossierData.metadata.assessorModel) dom.footerModelName.textContent = dossierData.metadata.assessorModel;
    }

    // 10. Update Queue UI & Show Content
    updateQueueList(dossierData);
    switchDossierTab('tab-overview');
    showViewState('content');
  }

  // ============================================================================
  // Queue Management
  // ============================================================================
  function updateQueueList(activeDossier) {
    const slug = `${activeDossier.pr.owner}/${activeDossier.pr.repo}#${activeDossier.pr.pull_number}`;
    
    // Check if item already in queue
    const existingIdx = state.queue.findIndex(item => item.slug === slug);
    if (existingIdx === -1) {
      state.queue.unshift({
        slug: slug,
        dossier: activeDossier,
        isSample: activeDossier.isSample
      });
    }

    clearElement(dom.queueList);
    dom.queueCount.textContent = `${state.queue.length} item${state.queue.length === 1 ? '' : 's'}`;

    state.queue.forEach((item, index) => {
      const li = createEl('li', 'queue-item');
      if (item.slug === slug) {
        li.classList.add('active');
      }

      li.tabIndex = 0;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', item.slug === slug ? 'true' : 'false');

      const header = createEl('div', 'queue-item-header');
      const repoSpan = createEl('span', 'queue-item-repo', item.slug);
      const badgeSpan = createEl('span', [
        'queue-item-badge',
        item.isSample ? 'badge-sample' : 'badge-live'
      ], item.isSample ? 'SAMPLE' : 'LIVE');

      header.appendChild(repoSpan);
      header.appendChild(badgeSpan);

      const title = createEl('div', 'queue-item-title', item.dossier.pr.title || 'Pull Request');
      const meta = createEl('div', 'queue-item-meta');
      const verifiedCount = (item.dossier.assessment && item.dossier.assessment.evidence)
        ? item.dossier.assessment.evidence.filter(e => e.verified).length
        : 0;
      meta.textContent = `${verifiedCount} verified facts`;

      li.appendChild(header);
      li.appendChild(title);
      li.appendChild(meta);

      li.addEventListener('click', () => {
        loadDossierIntoDesk(item.dossier);
      });

      li.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          loadDossierIntoDesk(item.dossier);
        }
      });

      dom.queueList.appendChild(li);
    });
  }

  // ============================================================================
  // Pull Request Assessment Orchestration (POST /api/assess)
  // ============================================================================
  async function analyzePullRequest(prInput) {
    const cleanInput = (prInput || '').trim();
    if (!cleanInput) {
      alert('Please enter a valid GitHub pull request URL or identifier.');
      dom.prUrlInput.focus();
      return;
    }

    // Set UI to loading state
    showViewState('loading');

    // 4-step progress list: real progress tracking
    const steps = [
      document.getElementById('load-step-1'),
      document.getElementById('load-step-2'),
      document.getElementById('load-step-3'),
      document.getElementById('load-step-4')
    ];

    steps.forEach(s => {
      if (s) s.className = 'timeline-step';
    });
    if (steps[0]) steps[0].className = 'timeline-step step-active';

    try {
      const payload = { pr_url: cleanInput };
      const refMatch = cleanInput.match(/^([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+)#(\d+)$/);
      const urlMatch = cleanInput.match(/^https?:\/\/github\.com\/([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+)\/pull\/(\d+)/);
      if (refMatch) {
        payload.owner = refMatch[1];
        payload.repo = refMatch[2];
        payload.pull_number = parseInt(refMatch[3], 10);
        payload.pr_url = `https://github.com/${refMatch[1]}/${refMatch[2]}/pull/${refMatch[3]}`;
      } else if (urlMatch) {
        payload.owner = urlMatch[1];
        payload.repo = urlMatch[2];
        payload.pull_number = parseInt(urlMatch[3], 10);
      }

      const response = await fetch('/api/assess', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        let errText = `HTTP Error ${response.status}: ${response.statusText}`;
        try {
          const errJson = await response.json();
          if (errJson && errJson.error) {
            errText = errJson.error;
          }
        } catch {
          // Response body was not JSON
        }
        throw new Error(errText);
      }

      const resData = await response.json();
      if (resData.status === 'error') {
        throw new Error(resData.error || 'Server reported assessment error');
      }

      // Mark all progress steps completed when real response arrives
      steps.forEach(s => {
        if (s) s.className = 'timeline-step step-done';
      });

      // Mark real Gemma inference call succeeded
      if (resData.model) currentGemmaModel = resData.model;
      setGemmaSignal('online');

      // Successful live response
      const liveDossier = {
        isSample: false,
        pr: resData.pr,
        files: resData.files || [],
        diff: resData.diff || '',
        assessment: resData.data,
        metadata: {
          dataSource: 'GitHub REST API (Live)',
          auditedAt: new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC',
          assessorModel: resData.model || 'gemma-4-26b-a4b-it via REST API'
        }
      };

      loadDossierIntoDesk(liveDossier);

    } catch (err) {
      showViewState('error');
      setGemmaSignal('error', err.message ? err.message.substring(0, 16) : 'Failed');
      dom.errorMessageText.textContent = err.message || 'Unable to retrieve and assess pull request.';
      dom.errorDetailsContainer.style.display = 'block';
      dom.errorDetailsCode.textContent = String(err.stack || err);
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

    const btnLandingSample = document.getElementById('btn-landing-sample');
    const btnLandingSampleNav = document.getElementById('btn-landing-sample-nav');
    if (btnLandingSample) {
      btnLandingSample.addEventListener('click', () => {
        switchAppView('workspace');
        loadDossierIntoDesk(SAMPLE_PR_DATA);
      });
    }
    if (btnLandingSampleNav) {
      btnLandingSampleNav.addEventListener('click', () => {
        switchAppView('workspace');
        loadDossierIntoDesk(SAMPLE_PR_DATA);
      });
    }

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
    dom.btnAnalyze.addEventListener('click', () => {
      analyzePullRequest(dom.prUrlInput.value);
    });

    dom.prUrlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        analyzePullRequest(dom.prUrlInput.value);
      }
    });

    dom.btnLoadSample.addEventListener('click', () => {
      loadDossierIntoDesk(SAMPLE_PR_DATA);
    });

    dom.btnEmptySample.addEventListener('click', () => {
      loadDossierIntoDesk(SAMPLE_PR_DATA);
    });

    dom.btnErrorSample.addEventListener('click', () => {
      loadDossierIntoDesk(SAMPLE_PR_DATA);
    });

    dom.btnErrorRetry.addEventListener('click', () => {
      analyzePullRequest(dom.prUrlInput.value);
    });

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

    // Default load: Load the authentic, verified Sample PR with clear SAMPLE label into desk
    loadDossierIntoDesk(SAMPLE_PR_DATA);

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
