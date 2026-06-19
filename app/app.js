const DATASET_KEY = "toeic-study.dataset.v1";
const PROGRESS_KEY = "toeic-study.progress.v1";
const SESSION_KEY = "toeic-study.session.v1";

const state = {
  dataset: { version: 1, stats: {}, items: [] },
  progress: { version: 1, attempts: [], itemStats: {}, createdAt: new Date().toISOString() },
  mode: "mixed",
  questionType: "all",
  practiceStarted: false,
  current: null,
  answered: false,
  questionStartedAt: 0,
  timerId: null,
  lastAttemptId: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const QUESTION_TYPES = {
  all: "혼합",
  meaning: "단어→뜻",
  term: "뜻→단어",
  word: "영단어",
  conjunction: "접속사",
  preposition: "전치사",
  tense: "시제",
};

const els = {
  dataStatus: $("#dataStatus"),
  metricItems: $("#metricItems"),
  metricAccuracy: $("#metricAccuracy"),
  metricWeak: $("#metricWeak"),
  practiceHome: $("#practiceHome"),
  homeSummary: $("#homeSummary"),
  homeTotal: $("#homeTotal"),
  homeMeaning: $("#homeMeaning"),
  homeTerm: $("#homeTerm"),
  homeWeak: $("#homeWeak"),
  emptyState: $("#emptyState"),
  questionCard: $("#questionCard"),
  questionSource: $("#questionSource"),
  questionTags: $("#questionTags"),
  questionTimer: $("#questionTimer"),
  questionSentence: $("#questionSentence"),
  questionPrompt: $("#questionPrompt"),
  choices: $("#choices"),
  answerPanel: $("#answerPanel"),
  answerText: $("#answerText"),
  emptyStateText: $("#emptyStateText"),
  blankSentence: $("#blankSentence"),
  sentenceKo: $("#sentenceKo"),
  grammarNote: $("#grammarNote"),
  currentTerm: $("#currentTerm"),
  detailSeen: $("#detailSeen"),
  detailWrong: $("#detailWrong"),
  detailStreak: $("#detailStreak"),
  detailUnsure: $("#detailUnsure"),
  detailLastTime: $("#detailLastTime"),
  detailAvgTime: $("#detailAvgTime"),
  recentWrongList: $("#recentWrongList"),
  weakTable: $("#weakTable"),
  weakSearch: $("#weakSearch"),
  exportWeakButton: $("#exportWeakButton"),
  statAttempts: $("#statAttempts"),
  statForgetting: $("#statForgetting"),
  statAvgTime: $("#statAvgTime"),
  tagBars: $("#tagBars"),
  datasetSummary: $("#datasetSummary"),
  progressSummary: $("#progressSummary"),
  datasetInput: $("#datasetInput"),
  progressInput: $("#progressInput"),
  fullscreenButton: $("#fullscreenButton"),
  fullscreenIcon: $("#fullscreenIcon"),
};

function safeParse(value, fallback) {
  try {
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

function saveProgress() {
  localStorage.setItem(PROGRESS_KEY, JSON.stringify(state.progress));
}

function saveDataset() {
  localStorage.setItem(DATASET_KEY, JSON.stringify(state.dataset));
}

function pct(value) {
  return `${Math.round(value * 100)}%`;
}

function itemStats(itemId) {
  if (!state.progress.itemStats[itemId]) {
    state.progress.itemStats[itemId] = {
      seen: 0,
      correct: 0,
      wrong: 0,
      streak: 0,
      lastSeenAt: null,
      lastWrongAt: null,
      lastTimeMs: 0,
      totalTimeMs: 0,
      uncertain: 0,
      flagged: false,
    };
  }
  return state.progress.itemStats[itemId];
}

function existingItemStats(itemId) {
  return state.progress.itemStats[itemId] || null;
}

function normalizeDataset(raw) {
  const items = Array.isArray(raw?.items) ? raw.items : [];
  const cleanItems = items
    .filter((item) => item && item.id && item.term && item.answer && item.sentence)
    .map((item) => {
      const choices = Array.isArray(item.choices) && item.choices.length >= 2
        ? item.choices
        : buildFallbackChoices(item.answer);
      let answerIndex = Number.isInteger(item.answerIndex) ? item.answerIndex : choices.indexOf(item.answer);
      if (answerIndex < 0) {
        choices[0] = item.answer;
        answerIndex = 0;
      }
      return {
        id: String(item.id),
        term: String(item.term),
        termKey: item.termKey ? String(item.termKey) : normalizeTermKey(item.term),
        contextId: item.contextId ? String(item.contextId) : `ctx-${stableHash(item.sentence)}`,
        questionType: normalizeQuestionType(item.questionType || item.type || inferQuestionType(item)),
        answer: String(item.answer),
        choices: choices.map(String),
        answerIndex,
        tags: Array.isArray(item.tags) ? item.tags.map(String) : ["general"],
        source: item.source ? String(item.source) : "unknown",
        sentence: String(item.sentence),
        contextType: item.contextType ? String(item.contextType) : (String(item.sentence).length > 180 ? "paragraph" : "sentence"),
        blankSentence: item.blankSentence ? String(item.blankSentence) : String(item.sentence),
        sentenceKo: item.sentenceKo ? String(item.sentenceKo) : "",
        grammarFocus: item.grammarFocus ? String(item.grammarFocus) : "",
        grammarNote: item.grammarNote ? String(item.grammarNote) : "",
        quality: item.quality ? String(item.quality) : "unverified",
        prompt: item.prompt ? String(item.prompt) : defaultPrompt(item),
      };
    });
  return {
    version: 1,
    stats: {
      ...(raw?.stats || {}),
      itemCount: cleanItems.length,
    },
    items: cleanItems,
  };
}

function isStudyReadyDataset(dataset) {
  const items = Array.isArray(dataset?.items) ? dataset.items : [];
  if (!items.length) return false;
  return items.every((item) => {
    const quality = String(item.quality || "");
    return (quality === "approved" || quality === "sample")
      && Boolean(item.sentenceKo)
      && Boolean(item.grammarNote)
      && Array.isArray(item.choices)
      && item.choices.includes(item.answer);
  });
}

function buildFallbackChoices(answer) {
  const defaults = ["시행하다", "연기하다", "검토하다", "제출하다"].filter((choice) => choice !== answer);
  return [answer, ...defaults].slice(0, 4);
}

function normalizeQuestionType(value) {
  const type = String(value || "meaning").trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(QUESTION_TYPES, type) && type !== "all" ? type : "meaning";
}

function inferQuestionType(item) {
  const focus = String(item?.grammarFocus || "").toLowerCase();
  if (focus.includes("conjunction")) return "conjunction";
  if (focus.includes("preposition")) return "preposition";
  if (focus.includes("tense")) return "tense";
  return "meaning";
}

function defaultPrompt(item) {
  const type = normalizeQuestionType(item.questionType || item.type || inferQuestionType(item));
  if (type === "meaning") return `문맥상 ${item.term}의 뜻은?`;
  if (type === "term") return "뜻에 맞는 영어 단어는?";
  if (type === "word") return "빈칸에 들어갈 가장 알맞은 영단어는?";
  if (type === "conjunction") return "빈칸에 들어갈 가장 알맞은 접속사는?";
  if (type === "preposition") return "빈칸에 들어갈 가장 알맞은 전치사는?";
  if (type === "tense") return "빈칸에 들어갈 가장 알맞은 동사 형태는?";
  return "빈칸에 들어갈 가장 알맞은 표현은?";
}

async function loadInitialDataset() {
  const localApproved = await fetchDatasetCandidate("../private-data/generated/study-items.approved.json");
  if (localApproved) {
    state.dataset = localApproved;
    saveDataset();
    return "로컬 추출 데이터";
  }

  const saved = safeParse(localStorage.getItem(DATASET_KEY), null);
  if (saved?.items?.length) {
    const normalized = normalizeDataset(saved);
    if (isStudyReadyDataset(normalized)) {
      state.dataset = normalized;
      return "브라우저 저장 데이터";
    }
    localStorage.removeItem(DATASET_KEY);
  }

  const sample = await fetchDatasetCandidate("./sample-items.json");
  if (sample) {
    state.dataset = sample;
    return "샘플 데이터";
  }
  return "데이터 없음";
}

async function fetchDatasetCandidate(url) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    const data = await response.json();
    const normalized = normalizeDataset(data);
    return isStudyReadyDataset(normalized) ? normalized : null;
  } catch {
    return null;
  }
}

function loadProgress() {
  const saved = safeParse(localStorage.getItem(PROGRESS_KEY), null);
  if (saved?.version && saved.itemStats && Array.isArray(saved.attempts)) {
    state.progress = saved;
  }
}

function weightedScore(item) {
  const stats = existingItemStats(item.id) || {
    seen: 0,
    correct: 0,
    wrong: 0,
    streak: 0,
    lastSeenAt: null,
    lastWrongAt: null,
    lastTimeMs: 0,
    totalTimeMs: 0,
    uncertain: 0,
    flagged: false,
  };
  const aggregate = termStats(item.termKey, false);
  const seenWeight = stats.seen === 0 ? 12 : 0;
  const wrongRate = stats.seen ? stats.wrong / stats.seen : 0;
  const unsureBoost = (stats.uncertain || 0) * 5 + (stats.flagged ? 12 : 0) + (aggregate.uncertain || 0) * 2;
  const slowBoost = stats.seen && averageTimeMs(stats) > 12000 ? 4 : 0;
  const recency = stats.lastSeenAt ? Math.max(0, 8 - (Date.now() - new Date(stats.lastSeenAt).getTime()) / 86400000) : 0;
  const modeBoost = state.mode === "weak" ? (stats.wrong + aggregate.wrong) * 8 + wrongRate * 15 + unsureBoost : 0;
  const newBoost = state.mode === "new" && stats.seen === 0 ? 20 : 0;
  return seenWeight + stats.wrong * 3 + wrongRate * 10 + unsureBoost + slowBoost + modeBoost + newBoost - recency + Math.random();
}

function isWeakItem(item) {
  const stats = existingItemStats(item.id);
  return isWeakStats(stats) || isWeakStats(termStats(item.termKey, false));
}

function isNewItem(item) {
  return termStats(item.termKey, false).seen === 0;
}

function chooseWeighted(pool) {
  if (!pool.length) return null;
  return [...pool].sort((a, b) => weightedScore(b) - weightedScore(a))[0];
}

function todayPool(items) {
  const weak = items.filter(isWeakItem);
  const fresh = items.filter(isNewItem);
  const review = items.filter((item) => !isWeakItem(item) && !isNewItem(item));

  if (weak.length && fresh.length) {
    return Math.random() < 0.6 ? weak : fresh;
  }
  if (weak.length) return weak;
  if (fresh.length) return fresh;
  return review.length ? review : items;
}

function modeItems(items = filteredItems()) {
  if (state.mode === "all") return items;
  if (state.mode === "weak") return items.filter(isWeakItem);
  if (state.mode === "new") return items.filter(isNewItem);
  if (state.mode === "paragraph") {
    return items.filter((item) => item.contextType === "paragraph" || item.sentence.length > 180);
  }
  if (state.mode === "mixed") {
    const byId = new Map();
    items.filter(isWeakItem).forEach((item) => byId.set(item.id, item));
    items.filter(isNewItem).forEach((item) => byId.set(item.id, item));
    return byId.size ? Array.from(byId.values()) : items;
  }
  return items;
}

function pickNextItem() {
  const items = filteredItems();
  if (!items.length) return null;
  if (state.mode === "all") return items[Math.floor(Math.random() * items.length)];

  let pool = modeItems(items);
  if (state.mode === "mixed") {
    pool = todayPool(items);
  }
  if (state.mode === "paragraph") {
    const paragraphs = items.filter((item) => item.contextType === "paragraph" || item.sentence.length > 180);
    pool = paragraphs.length ? paragraphs : items;
  }
  return chooseWeighted(pool);
}

function filteredItems() {
  if (state.questionType === "all") return state.dataset.items;
  return state.dataset.items.filter((item) => item.questionType === state.questionType);
}

function renderCurrent() {
  const item = state.current;
  const hasDataset = state.dataset.items.length > 0;
  const hasQuestion = state.practiceStarted && Boolean(item);
  els.practiceHome?.classList.toggle("hidden", state.practiceStarted || !hasDataset);
  els.emptyState.classList.toggle("hidden", hasQuestion || (!state.practiceStarted && hasDataset));
  els.questionCard.classList.toggle("hidden", !hasQuestion);
  if (!hasQuestion) {
    stopTimer();
    state.answered = false;
    state.lastAttemptId = null;
    state.questionStartedAt = 0;
    els.answerPanel.classList.add("hidden");
    els.questionSource.textContent = "-";
    els.questionTags.textContent = "-";
    els.questionTimer.textContent = "0초";
    els.questionSentence.textContent = "";
    els.questionPrompt.textContent = "";
    els.answerText.textContent = "";
    els.blankSentence.textContent = "";
    els.sentenceKo.textContent = "";
    els.grammarNote.textContent = "";
    els.choices.innerHTML = "";
    renderEmptyState();
    renderCurrentStats();
    return;
  }

  state.answered = false;
  state.lastAttemptId = null;
  startTimer();
  els.answerPanel.classList.add("hidden");
  els.questionSource.textContent = item.source;
  els.questionTags.textContent = [QUESTION_TYPES[item.questionType], item.quality, ...item.tags].filter(Boolean).join(" · ");
  els.questionSentence.classList.toggle("paragraph", item.contextType === "paragraph" || item.sentence.length > 180);
  els.questionSentence.innerHTML = renderQuestionSentence(item);
  els.questionPrompt.textContent = item.prompt;
  els.currentTerm.textContent = currentItemLabel(item);
  els.answerText.textContent = item.answer;
  els.blankSentence.textContent = answerSentenceLine(item);
  els.sentenceKo.textContent = item.sentenceKo || "문장 해석 데이터 없음";
  els.grammarNote.textContent = item.grammarNote || "문법 포인트 데이터 없음";

  els.choices.innerHTML = "";
  item.choices.forEach((choice, index) => {
    const button = document.createElement("button");
    button.className = "choice-button";
    button.type = "button";
    button.textContent = choice;
    button.addEventListener("click", () => answerCurrent(index, button));
    els.choices.appendChild(button);
  });
  renderCurrentStats();
}

function renderEmptyState() {
  if (!els.emptyStateText) return;
  if (!state.dataset.items.length) {
    els.emptyStateText.textContent = "자료 탭에서 `study-items.json`을 가져오세요.";
    return;
  }
  if (state.mode === "weak") {
    els.emptyStateText.textContent = "아직 약점으로 저장된 단어가 없습니다. 틀리거나, 헷갈림/복습 체크를 한 단어가 생기면 여기서 집중 연습할 수 있습니다.";
    return;
  }
  if (state.mode === "new") {
    els.emptyStateText.textContent = "선택한 범위의 새 단어를 모두 풀었습니다. 오늘 모드나 전체 모드로 복습하세요.";
    return;
  }
  els.emptyStateText.textContent = `${QUESTION_TYPES[state.questionType] || "선택한 유형"} 유형의 학습 데이터가 없습니다.`;
}

function renderQuestionSentence(item) {
  if (item.questionType === "meaning") return highlightTerm(item.sentence, item.term);
  return highlightBlank(item.blankSentence || item.sentence);
}

function highlightBlank(sentence) {
  const safe = escapeHtml(sentence || "");
  if (safe.includes("_____")) return safe.replace("_____", "<mark>_____</mark>");
  return safe;
}

function currentItemLabel(item) {
  if (item.questionType === "meaning") return item.term;
  if (item.questionType === "term") return item.answer;
  return `${QUESTION_TYPES[item.questionType]} · ${item.answer}`;
}

function answerSentenceLine(item) {
  if (item.questionType === "meaning") return item.blankSentence;
  if (item.questionType === "term") return `정답 단어: ${item.answer} · 뜻: ${item.sentence}`;
  return `정답 문장: ${item.sentence}`;
}

function highlightTerm(sentence, term) {
  const escaped = escapeRegExp(term);
  const pattern = new RegExp(`\\b(${escaped})\\b`, "i");
  if (pattern.test(sentence)) {
    return escapeHtml(sentence).replace(pattern, "<mark>$1</mark>");
  }
  return `${escapeHtml(sentence)} <mark>${escapeHtml(term)}</mark>`;
}

function answerCurrent(index) {
  if (!state.current || state.answered) return;
  state.answered = true;
  const item = state.current;
  const correct = index === item.answerIndex;
  const now = new Date().toISOString();
  const elapsedMs = Math.max(0, Date.now() - state.questionStartedAt);
  stopTimer();
  const stats = itemStats(item.id);
  stats.seen += 1;
  stats.correct += correct ? 1 : 0;
  stats.wrong += correct ? 0 : 1;
  stats.streak = correct ? stats.streak + 1 : 0;
  stats.lastSeenAt = now;
  stats.lastTimeMs = elapsedMs;
  stats.totalTimeMs = (stats.totalTimeMs || 0) + elapsedMs;
  if (!correct) stats.lastWrongAt = now;
  const attemptId = `${Date.now()}-${item.id}`;
  state.lastAttemptId = attemptId;
  state.progress.attempts.unshift({
    id: attemptId,
    itemId: item.id,
    term: item.term,
    answer: item.answer,
    chosen: item.choices[index],
    correct,
    uncertain: false,
    flagged: false,
    timeMs: elapsedMs,
    tags: item.tags,
    termKey: item.termKey,
    contextId: item.contextId,
    questionType: item.questionType,
    at: now,
  });
  state.progress.attempts = state.progress.attempts.slice(0, 1000);
  saveProgress();

  $$(".choice-button").forEach((button, choiceIndex) => {
    if (choiceIndex === item.answerIndex) button.classList.add("correct");
    if (choiceIndex === index && !correct) button.classList.add("wrong");
  });
  els.answerPanel.classList.remove("hidden");
  updateSelfCheckButtons();
  renderAll();
}

function nextQuestion() {
  state.practiceStarted = true;
  state.current = pickNextItem();
  sessionStorage.setItem(SESSION_KEY, state.current?.id || "");
  renderCurrent();
  renderAll();
}

function showPracticeHome() {
  state.practiceStarted = false;
  state.current = null;
  state.answered = false;
  state.lastAttemptId = null;
  sessionStorage.removeItem(SESSION_KEY);
  renderCurrent();
  renderAll();
}

function setActiveMode(mode) {
  state.mode = mode;
  $$(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
}

function setActiveQuestionType(type) {
  state.questionType = type;
  $$(".type-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.type === type);
  });
}

function renderCurrentStats() {
  if (!state.current) {
    els.currentTerm.textContent = "-";
    els.detailSeen.textContent = "0";
    els.detailWrong.textContent = "0";
    els.detailStreak.textContent = "0";
    els.detailUnsure.textContent = "0";
    els.detailLastTime.textContent = "-";
    els.detailAvgTime.textContent = "-";
    return;
  }
  const stats = termStats(state.current.termKey);
  els.detailSeen.textContent = String(stats.seen);
  els.detailWrong.textContent = String(stats.wrong);
  els.detailStreak.textContent = String(stats.streak);
  els.detailUnsure.textContent = String(stats.uncertain || 0);
  els.detailLastTime.textContent = stats.lastTimeMs ? formatTime(stats.lastTimeMs) : "-";
  els.detailAvgTime.textContent = stats.seen ? formatTime(averageTimeMs(stats)) : "-";
}

function renderMetrics() {
  const attempts = state.progress.attempts;
  const correct = attempts.filter((attempt) => attempt.correct).length;
  const visibleItems = filteredItems();
  const activeItems = modeItems(visibleItems);
  const weakCount = weakItems(visibleItems).length;
  els.metricItems.textContent = state.questionType === "all" && state.mode === "all"
    ? String(state.dataset.items.length)
    : `${activeItems.length}/${state.dataset.items.length}`;
  els.metricAccuracy.textContent = attempts.length ? pct(correct / attempts.length) : "0%";
  els.metricWeak.textContent = String(weakCount);
  els.dataStatus.textContent = `${state.dataset.items.length}개 항목`;
}

function renderHome() {
  if (!els.practiceHome) return;
  const total = state.dataset.items.length;
  const attempts = state.progress.attempts.length;
  const meaningCount = state.dataset.items.filter((item) => item.questionType === "meaning").length;
  const termCount = state.dataset.items.filter((item) => item.questionType === "term").length;
  const weakCount = weakItems().length;
  const activeCount = modeItems().length;
  const modeLabel = state.mode === "mixed"
    ? "오늘 조합"
    : state.mode === "weak"
      ? "약점만"
      : state.mode === "new"
        ? "새 단어"
        : state.mode === "paragraph"
          ? "문단"
          : "전체";
  els.homeTotal.textContent = String(total);
  els.homeMeaning.textContent = String(meaningCount);
  els.homeTerm.textContent = String(termCount);
  els.homeWeak.textContent = String(weakCount);
  els.homeSummary.textContent = attempts
    ? `${attempts}회 풀었습니다. ${modeLabel}에서 지금 풀 수 있는 문제는 ${activeCount}개입니다.`
    : `${modeLabel}에서 지금 풀 수 있는 문제는 ${activeCount}개입니다.`;
}

function weakItems(items = state.dataset.items) {
  return aggregateTermRows(items)
    .filter(({ stats }) => isWeakStats(stats))
    .sort((a, b) => {
      const aScore = b.stats.wrong - a.stats.wrong;
      if (aScore) return aScore;
      const unsureScore = (b.stats.uncertain || 0) - (a.stats.uncertain || 0);
      if (unsureScore) return unsureScore;
      return a.term.localeCompare(b.term);
    });
}

function renderRecentWrong() {
  const wrong = state.progress.attempts.filter((attempt) => !attempt.correct).slice(0, 6);
  els.recentWrongList.innerHTML = "";
  if (!wrong.length) {
    const li = document.createElement("li");
    li.textContent = "아직 오답 없음";
    els.recentWrongList.appendChild(li);
    return;
  }
  wrong.forEach((attempt) => {
    const li = document.createElement("li");
    const term = document.createElement("strong");
    term.textContent = attempt.term;
    const answer = document.createElement("span");
    answer.textContent = attempt.answer;
    li.append(term, answer);
    els.recentWrongList.appendChild(li);
  });
}

function renderWeakTable() {
  const query = els.weakSearch.value.trim().toLowerCase();
  const rows = weakItems().filter((row) => {
    const haystack = `${row.term} ${row.answers.join(" ")} ${row.tags.join(" ")}`.toLowerCase();
    return !query || haystack.includes(query);
  });
  els.weakTable.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.textContent = "표시할 약점 단어가 없습니다.";
    tr.appendChild(td);
    els.weakTable.appendChild(tr);
    return;
  }
  rows.forEach((row) => {
    const stats = row.stats;
    const tr = document.createElement("tr");
    const accuracy = stats.seen ? stats.correct / stats.seen : 0;
    [
      row.term,
      row.answers.join(" / "),
      String(stats.wrong),
      String(stats.uncertain || 0),
      stats.seen ? formatTime(averageTimeMs(stats)) : "-",
      pct(accuracy),
      row.tags.join(", "),
    ].forEach((text) => {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    });
    els.weakTable.appendChild(tr);
  });
}

function renderStats() {
  const attempts = state.progress.attempts;
  els.statAttempts.textContent = String(attempts.length);
  els.statForgetting.textContent = String(weakItems().length);
  const timed = attempts.filter((attempt) => Number.isFinite(attempt.timeMs) && attempt.timeMs > 0);
  const avgTime = timed.length ? timed.reduce((sum, attempt) => sum + attempt.timeMs, 0) / timed.length : 0;
  els.statAvgTime.textContent = formatTime(avgTime);
  const wrongTags = {};
  attempts.filter((attempt) => !attempt.correct).forEach((attempt) => {
    [attempt.questionType ? QUESTION_TYPES[attempt.questionType] : null, ...(Array.isArray(attempt.tags) ? attempt.tags : [])]
      .filter(Boolean)
      .forEach((tag) => {
      wrongTags[tag] = (wrongTags[tag] || 0) + 1;
    });
  });
  const entries = Object.entries(wrongTags).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const max = entries[0]?.[1] || 1;
  els.tagBars.innerHTML = "";
  if (!entries.length) {
    els.tagBars.textContent = "오답 태그가 아직 없습니다.";
    return;
  }
  entries.forEach(([tag, count]) => {
    const row = document.createElement("div");
    row.className = "tag-bar";
    row.innerHTML = `
      <span>${escapeHtml(tag)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(8, (count / max) * 100)}%"></div></div>
      <strong>${count}</strong>
    `;
    els.tagBars.appendChild(row);
  });
}

function renderDataView() {
  const stats = state.dataset.stats || {};
  els.datasetSummary.textContent = `${state.dataset.items.length}개 항목 · ${stats.sourceFileCount ?? 0}개 원본 기준`;
  const attempts = state.progress.attempts.length;
  const weak = weakItems().length;
  els.progressSummary.textContent = `${attempts}회 풀이 · 약점 ${weak}개`;
}

function isWeakStats(stats) {
  if (!stats) return false;
  const accuracy = stats.seen ? stats.correct / stats.seen : 1;
  return stats.flagged
    || (stats.uncertain || 0) > 0
    || stats.wrong > 0
    || (stats.seen >= 2 && accuracy < 0.75);
}

function termStats(termKey, create = true) {
  return aggregateStats(
    state.dataset.items
      .filter((item) => item.termKey === termKey)
      .map((item) => create ? itemStats(item.id) : existingItemStats(item.id))
      .filter(Boolean)
  );
}

function aggregateTermRows(items = state.dataset.items) {
  const rows = new Map();
  items.forEach((item) => {
    if (!rows.has(item.termKey)) {
      rows.set(item.termKey, {
        term: item.term,
        answers: new Set(),
        tags: new Set(),
        questionTypes: new Set(),
        itemIds: [],
      });
    }
    const row = rows.get(item.termKey);
    row.answers.add(item.answer);
    item.tags.forEach((tag) => row.tags.add(tag));
    row.questionTypes.add(item.questionType);
    row.itemIds.push(item.id);
  });
  return Array.from(rows.values()).map((row) => ({
    term: row.term,
    answers: Array.from(row.answers),
    tags: [...Array.from(row.questionTypes).map((type) => QUESTION_TYPES[type]).filter(Boolean), ...Array.from(row.tags)],
    stats: aggregateStats(row.itemIds.map((id) => existingItemStats(id)).filter(Boolean)),
  }));
}

function aggregateStats(statsList) {
  return statsList.reduce((total, stats) => {
    total.seen += stats.seen || 0;
    total.correct += stats.correct || 0;
    total.wrong += stats.wrong || 0;
    total.uncertain += stats.uncertain || 0;
    total.totalTimeMs += stats.totalTimeMs || 0;
    total.flagged = total.flagged || Boolean(stats.flagged);
    if (stats.lastTimeMs && (!total.lastSeenAt || new Date(stats.lastSeenAt) > new Date(total.lastSeenAt))) {
      total.lastTimeMs = stats.lastTimeMs;
      total.lastSeenAt = stats.lastSeenAt;
    }
    total.streak = Math.max(total.streak, stats.streak || 0);
    return total;
  }, {
    seen: 0,
    correct: 0,
    wrong: 0,
    uncertain: 0,
    totalTimeMs: 0,
    lastTimeMs: 0,
    lastSeenAt: null,
    streak: 0,
    flagged: false,
  });
}

function averageTimeMs(stats) {
  return stats.seen ? (stats.totalTimeMs || 0) / stats.seen : 0;
}

function normalizeTermKey(term) {
  return String(term).trim().toLowerCase().replace(/\s+/g, " ");
}

function stableHash(value) {
  let hash = 0;
  const text = String(value);
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(36);
}

function formatTime(ms) {
  if (!ms) return "0초";
  if (ms < 1000) return "1초";
  const seconds = Math.round(ms / 100) / 10;
  return `${seconds}초`;
}

function startTimer() {
  stopTimer();
  state.questionStartedAt = Date.now();
  if (els.questionTimer) {
    els.questionTimer.textContent = "0초";
    state.timerId = window.setInterval(() => {
      els.questionTimer.textContent = formatTime(Date.now() - state.questionStartedAt);
    }, 500);
  }
}

function stopTimer() {
  if (state.timerId) {
    window.clearInterval(state.timerId);
    state.timerId = null;
  }
  if (els.questionTimer && state.questionStartedAt) {
    els.questionTimer.textContent = formatTime(Date.now() - state.questionStartedAt);
  }
}

function currentAttempt() {
  return state.progress.attempts.find((attempt) => attempt.id === state.lastAttemptId) || null;
}

function markCurrent(kind) {
  if (!state.current || !state.answered) return;
  const stats = itemStats(state.current.id);
  const attempt = currentAttempt();
  if (kind === "unsure" && attempt && !attempt.uncertain) {
    attempt.uncertain = true;
    attempt.flagged = true;
    stats.uncertain = (stats.uncertain || 0) + 1;
    stats.flagged = true;
  }
  if (kind === "flag") {
    stats.flagged = !stats.flagged;
    if (attempt) attempt.flagged = stats.flagged;
  }
  saveProgress();
  updateSelfCheckButtons();
  renderAll();
}

function updateSelfCheckButtons() {
  const unsureButton = $("#unsureButton");
  const flagButton = $("#flagButton");
  if (!state.current || !unsureButton || !flagButton) return;
  const stats = itemStats(state.current.id);
  const attempt = currentAttempt();
  unsureButton.disabled = !state.answered || Boolean(attempt?.uncertain);
  unsureButton.classList.toggle("active-check", Boolean(attempt?.uncertain));
  unsureButton.textContent = attempt?.uncertain ? "헷갈림 저장됨" : "맞혔지만 헷갈림";
  flagButton.classList.toggle("active-check", Boolean(stats.flagged));
  flagButton.textContent = stats.flagged ? "복습 체크됨" : "복습 체크";
}

function renderAll() {
  renderMetrics();
  renderHome();
  renderCurrentStats();
  renderRecentWrong();
  renderWeakTable();
  renderStats();
  renderDataView();
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function weakExportData() {
  const rows = weakItems().map((row) => ({
    term: row.term,
    answers: row.answers,
    tags: row.tags,
    stats: {
      seen: row.stats.seen,
      correct: row.stats.correct,
      wrong: row.stats.wrong,
      uncertain: row.stats.uncertain || 0,
      flagged: Boolean(row.stats.flagged),
      averageTimeMs: row.stats.seen ? Math.round(averageTimeMs(row.stats)) : 0,
      lastSeenAt: row.stats.lastSeenAt,
    },
  }));
  return {
    version: 1,
    exportedAt: new Date().toISOString(),
    itemCount: state.dataset.items.length,
    attemptCount: state.progress.attempts.length,
    weakCount: rows.length,
    rows,
  };
}

async function readJsonFile(file) {
  const text = await file.text();
  return JSON.parse(text);
}

function resetProgress() {
  if (!confirm("이 브라우저의 학습 기록을 초기화할까요?")) return;
  state.progress = { version: 1, attempts: [], itemStats: {}, createdAt: new Date().toISOString() };
  saveProgress();
  renderAll();
  renderCurrent();
}

function fullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

function fullscreenSupported() {
  const root = document.documentElement;
  const standardAllowed = document.fullscreenEnabled !== false && typeof root.requestFullscreen === "function";
  const webkitAllowed = document.webkitFullscreenEnabled !== false && typeof root.webkitRequestFullscreen === "function";
  return standardAllowed || webkitAllowed;
}

async function enterFullscreen() {
  const root = document.documentElement;
  const request = root.requestFullscreen || root.webkitRequestFullscreen;
  if (!request) return;
  await request.call(root);
}

async function exitFullscreen() {
  const exit = document.exitFullscreen || document.webkitExitFullscreen;
  if (!exit) return;
  await exit.call(document);
}

function updateFullscreenButton() {
  if (!els.fullscreenButton || !els.fullscreenIcon) return;
  const supported = fullscreenSupported();
  const active = Boolean(fullscreenElement());
  els.fullscreenButton.disabled = !supported;
  els.fullscreenButton.setAttribute("aria-pressed", active ? "true" : "false");
  els.fullscreenButton.setAttribute("aria-label", active ? "전체화면 해제" : "전체화면");
  els.fullscreenButton.title = supported
    ? (active ? "전체화면 해제" : "전체화면")
    : "이 브라우저는 전체화면을 지원하지 않습니다.";
  els.fullscreenIcon.textContent = active ? "×" : "⛶";
}

async function toggleFullscreen() {
  if (!fullscreenSupported()) {
    updateFullscreenButton();
    return;
  }
  try {
    if (fullscreenElement()) {
      await exitFullscreen();
    } else {
      await enterFullscreen();
    }
  } catch {
    // Browsers can reject fullscreen outside trusted user gestures.
  } finally {
    updateFullscreenButton();
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#039;",
  }[char]));
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function bindEvents() {
  $$(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".tab-button").forEach((item) => item.classList.remove("active"));
      $$(".view").forEach((view) => view.classList.remove("active"));
      button.classList.add("active");
      $(`#view-${button.dataset.view}`).classList.add("active");
      renderAll();
    });
  });

  $$(".mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveMode(button.dataset.mode);
      if (state.practiceStarted) {
        nextQuestion();
      } else {
        renderAll();
      }
    });
  });

  $$(".type-button").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveQuestionType(button.dataset.type);
      if (state.practiceStarted) {
        nextQuestion();
      } else {
        renderAll();
      }
    });
  });

  $$("[data-start-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveMode(button.dataset.startMode);
      setActiveQuestionType(button.dataset.startType);
      nextQuestion();
    });
  });

  $("#shuffleButton").addEventListener("click", nextQuestion);
  $("#skipButton").addEventListener("click", nextQuestion);
  $("#nextButton").addEventListener("click", nextQuestion);
  $("#unsureButton").addEventListener("click", () => markCurrent("unsure"));
  $("#flagButton").addEventListener("click", () => markCurrent("flag"));
  els.fullscreenButton?.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", updateFullscreenButton);
  document.addEventListener("webkitfullscreenchange", updateFullscreenButton);
  updateFullscreenButton();
  els.weakSearch.addEventListener("input", renderWeakTable);
  $("#exportDatasetButton").addEventListener("click", () => downloadJson("toeic-study-items.json", state.dataset));
  $("#exportProgressButton").addEventListener("click", () => downloadJson("toeic-study-progress.json", state.progress));
  els.exportWeakButton?.addEventListener("click", () => downloadJson("toeic-study-weak-words.json", weakExportData()));
  $("#resetProgressButton").addEventListener("click", resetProgress);

  els.datasetInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const raw = await readJsonFile(file);
    const normalized = normalizeDataset(raw);
    if (!isStudyReadyDataset(normalized)) {
      alert("이 파일은 완성 학습 데이터가 아닙니다. sentenceKo, grammarNote, quality=approved가 있는 검증 데이터만 가져옵니다.");
      event.target.value = "";
      return;
    }
    state.dataset = normalized;
    saveDataset();
    showPracticeHome();
    event.target.value = "";
  });

  els.progressInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const raw = await readJsonFile(file);
    if (!raw?.itemStats || !Array.isArray(raw.attempts)) {
      alert("학습 기록 파일 형식이 맞지 않습니다.");
      return;
    }
    state.progress = raw;
    saveProgress();
    renderAll();
    renderCurrent();
    event.target.value = "";
  });
}

async function init() {
  bindEvents();
  loadProgress();
  await loadInitialDataset();
  showPracticeHome();
  renderCurrent();
  renderAll();
}

init();
