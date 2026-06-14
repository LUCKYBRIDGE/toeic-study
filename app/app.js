const DATASET_KEY = "toeic-study.dataset.v1";
const PROGRESS_KEY = "toeic-study.progress.v1";
const SESSION_KEY = "toeic-study.session.v1";

const state = {
  dataset: { version: 1, stats: {}, items: [] },
  progress: { version: 1, attempts: [], itemStats: {}, createdAt: new Date().toISOString() },
  mode: "mixed",
  current: null,
  answered: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const els = {
  dataStatus: $("#dataStatus"),
  metricItems: $("#metricItems"),
  metricAccuracy: $("#metricAccuracy"),
  metricWeak: $("#metricWeak"),
  emptyState: $("#emptyState"),
  questionCard: $("#questionCard"),
  questionSource: $("#questionSource"),
  questionTags: $("#questionTags"),
  questionSentence: $("#questionSentence"),
  questionPrompt: $("#questionPrompt"),
  choices: $("#choices"),
  answerPanel: $("#answerPanel"),
  answerText: $("#answerText"),
  blankSentence: $("#blankSentence"),
  sentenceKo: $("#sentenceKo"),
  grammarNote: $("#grammarNote"),
  currentTerm: $("#currentTerm"),
  detailSeen: $("#detailSeen"),
  detailWrong: $("#detailWrong"),
  detailStreak: $("#detailStreak"),
  recentWrongList: $("#recentWrongList"),
  weakTable: $("#weakTable"),
  weakSearch: $("#weakSearch"),
  statAttempts: $("#statAttempts"),
  statForgetting: $("#statForgetting"),
  tagBars: $("#tagBars"),
  datasetSummary: $("#datasetSummary"),
  progressSummary: $("#progressSummary"),
  datasetInput: $("#datasetInput"),
  progressInput: $("#progressInput"),
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
    };
  }
  return state.progress.itemStats[itemId];
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
        answer: String(item.answer),
        choices: choices.map(String),
        answerIndex,
        tags: Array.isArray(item.tags) ? item.tags.map(String) : ["general"],
        source: item.source ? String(item.source) : "unknown",
        sentence: String(item.sentence),
        blankSentence: item.blankSentence ? String(item.blankSentence) : String(item.sentence),
        sentenceKo: item.sentenceKo ? String(item.sentenceKo) : "",
        grammarFocus: item.grammarFocus ? String(item.grammarFocus) : "",
        grammarNote: item.grammarNote ? String(item.grammarNote) : "",
        quality: item.quality ? String(item.quality) : "unverified",
        prompt: item.prompt ? String(item.prompt) : `문맥상 ${item.term}의 뜻은?`,
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

function buildFallbackChoices(answer) {
  const defaults = ["시행하다", "연기하다", "검토하다", "제출하다"].filter((choice) => choice !== answer);
  return [answer, ...defaults].slice(0, 4);
}

async function loadInitialDataset() {
  const saved = safeParse(localStorage.getItem(DATASET_KEY), null);
  if (saved?.items?.length) {
    state.dataset = normalizeDataset(saved);
    return "브라우저 저장 데이터";
  }

  const candidates = [
    "../private-data/generated/study-items.approved.json",
    "./sample-items.json",
  ];
  for (const url of candidates) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) continue;
      const data = await response.json();
      const normalized = normalizeDataset(data);
      if (normalized.items.length) {
        state.dataset = normalized;
        if (url.includes("private-data")) {
          saveDataset();
          return "로컬 추출 데이터";
        }
        return "샘플 데이터";
      }
    } catch {
      // Try next candidate.
    }
  }
  return "데이터 없음";
}

function loadProgress() {
  const saved = safeParse(localStorage.getItem(PROGRESS_KEY), null);
  if (saved?.version && saved.itemStats && Array.isArray(saved.attempts)) {
    state.progress = saved;
  }
}

function weightedScore(item) {
  const stats = itemStats(item.id);
  const seenWeight = stats.seen === 0 ? 12 : 0;
  const wrongRate = stats.seen ? stats.wrong / stats.seen : 0;
  const recency = stats.lastSeenAt ? Math.max(0, 8 - (Date.now() - new Date(stats.lastSeenAt).getTime()) / 86400000) : 0;
  const modeBoost = state.mode === "weak" ? stats.wrong * 8 + wrongRate * 15 : 0;
  const newBoost = state.mode === "new" && stats.seen === 0 ? 20 : 0;
  return seenWeight + stats.wrong * 3 + wrongRate * 10 + modeBoost + newBoost - recency + Math.random();
}

function pickNextItem() {
  const items = state.dataset.items;
  if (!items.length) return null;
  if (state.mode === "all") return items[Math.floor(Math.random() * items.length)];

  let pool = items;
  if (state.mode === "weak") {
    const weak = items.filter((item) => {
      const stats = itemStats(item.id);
      return stats.wrong > 0 || (stats.seen >= 2 && stats.correct / stats.seen < 0.75);
    });
    pool = weak.length ? weak : items;
  }
  if (state.mode === "new") {
    const unseen = items.filter((item) => itemStats(item.id).seen === 0);
    pool = unseen.length ? unseen : items;
  }
  return [...pool].sort((a, b) => weightedScore(b) - weightedScore(a))[0];
}

function renderCurrent() {
  const item = state.current;
  const hasData = Boolean(item);
  els.emptyState.classList.toggle("hidden", hasData);
  els.questionCard.classList.toggle("hidden", !hasData);
  if (!item) return;

  state.answered = false;
  els.answerPanel.classList.add("hidden");
  els.questionSource.textContent = item.source;
  els.questionTags.textContent = [item.quality, ...item.tags].filter(Boolean).join(" · ");
  els.questionSentence.innerHTML = highlightTerm(item.sentence, item.term);
  els.questionPrompt.textContent = item.prompt;
  els.currentTerm.textContent = item.term;
  els.answerText.textContent = item.answer;
  els.blankSentence.textContent = item.blankSentence;
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
  const stats = itemStats(item.id);
  stats.seen += 1;
  stats.correct += correct ? 1 : 0;
  stats.wrong += correct ? 0 : 1;
  stats.streak = correct ? stats.streak + 1 : 0;
  stats.lastSeenAt = now;
  if (!correct) stats.lastWrongAt = now;
  state.progress.attempts.unshift({
    itemId: item.id,
    term: item.term,
    answer: item.answer,
    chosen: item.choices[index],
    correct,
    tags: item.tags,
    at: now,
  });
  state.progress.attempts = state.progress.attempts.slice(0, 1000);
  saveProgress();

  $$(".choice-button").forEach((button, choiceIndex) => {
    if (choiceIndex === item.answerIndex) button.classList.add("correct");
    if (choiceIndex === index && !correct) button.classList.add("wrong");
  });
  els.answerPanel.classList.remove("hidden");
  renderAll();
}

function nextQuestion() {
  state.current = pickNextItem();
  sessionStorage.setItem(SESSION_KEY, state.current?.id || "");
  renderCurrent();
}

function renderCurrentStats() {
  if (!state.current) return;
  const stats = itemStats(state.current.id);
  els.detailSeen.textContent = String(stats.seen);
  els.detailWrong.textContent = String(stats.wrong);
  els.detailStreak.textContent = String(stats.streak);
}

function renderMetrics() {
  const attempts = state.progress.attempts;
  const correct = attempts.filter((attempt) => attempt.correct).length;
  const weakCount = weakItems().length;
  els.metricItems.textContent = String(state.dataset.items.length);
  els.metricAccuracy.textContent = attempts.length ? pct(correct / attempts.length) : "0%";
  els.metricWeak.textContent = String(weakCount);
  els.dataStatus.textContent = `${state.dataset.items.length}개 항목`;
}

function weakItems() {
  return state.dataset.items
    .map((item) => ({ item, stats: itemStats(item.id) }))
    .filter(({ stats }) => stats.wrong > 0 || (stats.seen >= 2 && stats.correct / stats.seen < 0.75))
    .sort((a, b) => b.stats.wrong - a.stats.wrong || a.item.term.localeCompare(b.item.term));
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
  const rows = weakItems().filter(({ item }) => {
    const haystack = `${item.term} ${item.answer} ${item.tags.join(" ")}`.toLowerCase();
    return !query || haystack.includes(query);
  });
  els.weakTable.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "표시할 약점 단어가 없습니다.";
    tr.appendChild(td);
    els.weakTable.appendChild(tr);
    return;
  }
  rows.forEach(({ item, stats }) => {
    const tr = document.createElement("tr");
    const accuracy = stats.seen ? stats.correct / stats.seen : 0;
    [item.term, item.answer, String(stats.wrong), pct(accuracy), item.tags.join(", ")].forEach((text) => {
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
  const wrongTags = {};
  attempts.filter((attempt) => !attempt.correct).forEach((attempt) => {
    attempt.tags.forEach((tag) => {
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

function renderAll() {
  renderMetrics();
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
      $$(".mode-button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.mode = button.dataset.mode;
      nextQuestion();
    });
  });

  $("#shuffleButton").addEventListener("click", nextQuestion);
  $("#skipButton").addEventListener("click", nextQuestion);
  $("#nextButton").addEventListener("click", nextQuestion);
  els.weakSearch.addEventListener("input", renderWeakTable);
  $("#exportDatasetButton").addEventListener("click", () => downloadJson("toeic-study-items.json", state.dataset));
  $("#exportProgressButton").addEventListener("click", () => downloadJson("toeic-study-progress.json", state.progress));
  $("#resetProgressButton").addEventListener("click", resetProgress);

  els.datasetInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const raw = await readJsonFile(file);
    state.dataset = normalizeDataset(raw);
    saveDataset();
    nextQuestion();
    renderAll();
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
  const lastId = sessionStorage.getItem(SESSION_KEY);
  state.current = state.dataset.items.find((item) => item.id === lastId) || pickNextItem();
  renderCurrent();
  renderAll();
}

init();
