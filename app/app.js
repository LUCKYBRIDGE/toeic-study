const DATASET_KEY = "toeic-study.dataset.v1";
const PROGRESS_KEY = "toeic-study.progress.v1";
const SESSION_KEY = "toeic-study.session.v1";

const DBStore = {
  dbName: "toeic_study_db",
  storeName: "cache_store",
  _open() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1);
      request.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName);
        }
      };
      request.onsuccess = (e) => resolve(e.target.result);
      request.onerror = (e) => reject(e.target.error);
    });
  },
  async get(key) {
    try {
      const db = await this._open();
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(this.storeName, "readonly");
        const store = transaction.objectStore(this.storeName);
        const request = store.get(key);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error);
      });
    } catch (e) {
      console.error("IndexedDB get error", e);
      return null;
    }
  },
  async set(key, val) {
    try {
      const db = await this._open();
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(this.storeName, "readwrite");
        const store = transaction.objectStore(this.storeName);
        const request = store.put(val, key);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
      });
    } catch (e) {
      console.error("IndexedDB set error", e);
    }
  },
  async remove(key) {
    try {
      const db = await this._open();
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(this.storeName, "readwrite");
        const store = transaction.objectStore(this.storeName);
        const request = store.delete(key);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
      });
    } catch (e) {
      console.error("IndexedDB remove error", e);
    }
  }
};


const state = {
  dataset: { version: 1, stats: {}, items: [] },
  progress: {
    version: 1,
    attempts: [],
    itemStats: {},
    createdAt: new Date().toISOString(),
    dailyGoal: 30,
    dailyCompleted: 0,
    streak: 0,
    lastActiveDate: null,
    activeDates: [],
    lastResetDate: null
  },
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
  homeUnseen: $("#homeUnseen"),
  homeMastered: $("#homeMastered"),
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
  streakCount: $("#streakCount"),
  dailyGoalSelect: $("#dailyGoalSelect"),
  excludeMasteredCheckbox: $("#excludeMasteredCheckbox"),
  progressBarFill: $("#progressBarFill"),
  progressText: $("#progressText"),
  successCard: $("#successCard"),
  successSolved: $("#successSolved"),
  successAccuracy: $("#successAccuracy"),
  successStreak: $("#successStreak"),
  successHomeButton: $("#successHomeButton"),
  successContinueButton: $("#successContinueButton"),
  streakCalendar: $("#streakCalendar"),
  syncLoader: $("#syncLoader"),
  userAccount: $("#userAccount"),
  userEmail: $("#userEmail"),
  gasStatusBanner: $("#gasStatusBanner"),
  appShell: $(".app-shell"),
  localDatasetLabel: $("#localDatasetLabel"),
  gasDatasetLabel: $("#gasDatasetLabel"),
  gasDatasetInput: $("#gasDatasetInput"),
  hintToggleButton: $("#hintToggleButton"),
  hintContentPanel: $("#hintContentPanel"),
  vocabDictionaryContainer: $("#vocabDictionaryContainer"),
  wordDetailDialog: $("#wordDetailDialog"),
  dialogWordTitle: $("#dialogWordTitle"),
  dialogWordBody: $("#dialogWordBody"),
  dialogCloseButton: $("#dialogCloseButton"),
};

function safeParse(value, fallback) {
  try {
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

function formatExplanationHtml(text) {
  if (!text) return "";
  
  function parseMarkdown(str) {
    return str
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .trim();
  }

  const lines = text.split("\n");
  let html = '<div class="explanation-container">';
  
  let currentCardType = null;
  let currentCardTitle = "";
  let currentCardBody = [];

  function flushCard() {
    if (currentCardType) {
      const bodyHtml = currentCardBody.join("<br>").trim();
      html += `
        <div class="exp-card ${currentCardType}">
          <div class="card-header">${currentCardTitle}</div>
          <div class="card-body">${bodyHtml}</div>
        </div>
      `;
      currentCardBody = [];
      currentCardType = null;
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) {
      if (currentCardType && currentCardBody.length > 0) {
        currentCardBody.push("");
      }
      continue;
    }

    if (line.includes("🎯 **주요 뜻** |") || line.startsWith("🎯 주요 뜻 |")) {
      flushCard();
      currentCardType = "primary-meaning";
      currentCardTitle = "🎯 주요 뜻";
      const val = line.split("|")[1] || "";
      currentCardBody.push(parseMarkdown(val));
    } else if (line.includes("📚 **보조 뜻** |") || line.startsWith("📚 보조 뜻 |")) {
      flushCard();
      currentCardType = "secondary-meaning";
      currentCardTitle = "📚 보조 뜻";
      const val = line.split("|")[1] || "";
      currentCardBody.push(parseMarkdown(val));
    } else if (line.includes("어휘 해설 |") || line.includes("해설 |")) {
      flushCard();
      currentCardType = "explanation";
      currentCardTitle = "💡 문제 해설";
      const val = line.split("|")[1] || "";
      currentCardBody.push(parseMarkdown(val));
    } else if (line.includes("오답 분석 |")) {
      flushCard();
      currentCardType = "wrong-analysis";
      currentCardTitle = "❌ 선택지 / 오답 분석";
      const val = line.split("|")[1] || "";
      if (val.trim()) {
        currentCardBody.push(parseMarkdown(val));
      }
    } else if (line.includes("토익 포인트 |") || line.includes("토익 비법 |")) {
      flushCard();
      currentCardType = "toeic-tip";
      currentCardTitle = "⭐ 토익 비법 / 꿀팁";
      const val = line.split("|")[1] || "";
      currentCardBody.push(parseMarkdown(val));
    } else if (line.startsWith("💡 **실전 적용 문맥**") || line.startsWith("💡 실전 적용 문맥")) {
      flushCard();
      currentCardType = "context-tip";
      currentCardTitle = "💡 실전 적용 문맥";
    } else {
      if (currentCardType) {
        if (line.startsWith("- ")) {
          currentCardBody.push(`<div class="list-item">${parseMarkdown(line.slice(2))}</div>`);
        } else {
          currentCardBody.push(parseMarkdown(line));
        }
      } else {
        html += `<p class="general-text">${parseMarkdown(line)}</p>`;
      }
    }
  }
  flushCard();
  
  html += '</div>';
  return html;
}

// 환경 감지 및 디바운스 설정 (Apps Script 연동 비활성화 - 로컬 및 GitHub Pages 전용 모드)
// const isGas = typeof google !== "undefined" && google.script && google.script.run;
const isGas = false;
let saveDebounceTimer = null;
let hasPendingSave = false;

// 로딩 마스크 헬퍼
function showSyncLoader(text) {
  if (els.syncLoader) {
    const txtEl = els.syncLoader.querySelector(".sync-text");
    if (txtEl && text) txtEl.textContent = text;
    els.syncLoader.classList.remove("hidden");
  }
}

function hideSyncLoader() {
  if (els.syncLoader) {
    els.syncLoader.classList.add("hidden");
  }
}

// 구글 백엔드 비동기 호출 래퍼
const GAS = {
  call(methodName, ...args) {
    return new Promise((resolve, reject) => {
      if (!isGas) {
        reject(new Error("Apps Script 환경이 아닙니다."));
        return;
      }
      google.script.run
        .withSuccessHandler(resolve)
        .withFailureHandler(err => {
          console.error(`GAS Call failed [${methodName}]:`, err);
          reject(err);
        })[methodName](...args);
    });
  }
};

// 추상화 스토리지 서비스
const Storage = {
  isGasEnv() {
    return isGas;
  },

  async loadDataset() {
    if (isGas) {
      if (els.gasDatasetLabel) els.gasDatasetLabel.classList.remove("hidden");
      if (els.localDatasetLabel) els.localDatasetLabel.classList.add("hidden");

      // 1. 브라우저 캐시에서 우선 로드 시도
      const cached = await DBStore.get(DATASET_KEY);
      if (cached?.items?.length) {
        return cached;
      }

      // 2. 캐시가 없는 최초 진입 시에만 구글 시트에서 가져오기
      showSyncLoader("단어 데이터를 불러오는 중...");
      try {
        const res = await GAS.call("getStudyDataset");
        const normalized = normalizeDataset(res);
        if (normalized?.items?.length) {
          await DBStore.set(DATASET_KEY, normalized);
          return normalized;
        }
      } catch (e) {
        console.error("GAS loadDataset error, fallback to samples.", e);
      } finally {
        hideSyncLoader();
      }
    }

    // 로컬 파일 또는 LocalStorage 폴백
    const localApproved = await fetchDatasetCandidate("../private-data/generated/study-items.approved.json");
    if (localApproved) {
      await DBStore.set(DATASET_KEY, localApproved);
      return localApproved;
    }

    const saved = await DBStore.get(DATASET_KEY);
    if (saved?.items?.length) {
      const normalized = normalizeDataset(saved);
      if (isStudyReadyDataset(normalized)) return normalized;
      await DBStore.remove(DATASET_KEY);
    }

    const sample = await fetchDatasetCandidate("./sample-items.json");
    if (sample) return sample;

    return { version: 1, stats: { itemCount: 0 }, items: [] };
  },

  async loadProgress() {
    if (isGas) {
      showSyncLoader("학습 진도를 가져오는 중...");
      try {
        const res = await GAS.call("getUserProgress");
        if (res.email) {
          // 사용자 계정 UI 업데이트
          if (els.userAccount && els.userEmail) {
            els.userEmail.textContent = res.email;
            els.userAccount.classList.remove("hidden");
          }
          if (els.gasStatusBanner) {
            els.gasStatusBanner.classList.remove("hidden");
          }
        }
        if (res.progress) {
          return res.progress;
        }
      } catch (e) {
        console.error("GAS loadProgress error", e);
      } finally {
        hideSyncLoader();
      }
    }

    // 로컬 LocalStorage 폴백
    const saved = safeParse(localStorage.getItem(PROGRESS_KEY), null);
    return saved || null;
  },

  saveProgress(progress, immediate = false) {
    if (isGas) {
      hasPendingSave = true;
      if (immediate) {
        this.flushProgress(progress);
      } else {
        // 3초 디바운스 적용
        if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
        saveDebounceTimer = setTimeout(() => {
          this.flushProgress(progress);
        }, 3000);
      }
    } else {
      localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
    }
  },

  async flushProgress(progress) {
    if (!isGas || !hasPendingSave) return;
    if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
    
    showSyncLoader("진도 저장 중...");
    try {
      const res = await GAS.call("saveUserProgress", JSON.stringify(progress));
      if (res.success) {
        hasPendingSave = false;
        console.log("GAS Progress saved at", res.updatedAt);
      } else {
        console.error("GAS Save failed:", res.message);
      }
    } catch (e) {
      console.error("GAS flushProgress error:", e);
    } finally {
      hideSyncLoader();
    }
  },

  async saveDataset(dataset) {
    if (!isGas) {
      await DBStore.set(DATASET_KEY, dataset);
    }
  }
};

function saveProgress(immediate = false) {
  Storage.saveProgress(state.progress, immediate);
}

async function saveDataset() {
  await Storage.saveDataset(state.dataset);
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

// 동일한 단어(termKey)의 모든 학습 문항들을 가져오는 함수
function getRelatedVocabItems(termKey) {
  if (!state.dataset?.items) return [];
  const key = normalizeTermKey(termKey);
  return state.dataset.items.filter(item => item.termKey === key);
}

// 다의어 사전 카드를 answerPanel 하단에 동적으로 렌더링하는 함수
function renderVocabDictionary(currentItem) {
  if (!els.vocabDictionaryContainer) return;
  els.vocabDictionaryContainer.innerHTML = "";

  const related = getRelatedVocabItems(currentItem.termKey);
  if (related.length <= 1) {
    return;
  }

  const container = document.createElement("div");
  container.className = "vocab-dictionary-wrapper";

  const title = document.createElement("h4");
  title.innerHTML = "💡 이 단어의 다른 출제 유형 및 쓰임새";
  container.appendChild(title);


  const list = document.createElement("div");
  list.className = "vocab-dict-list";

  related.forEach(item => {
    const card = document.createElement("div");
    const isCurrent = item.id === currentItem.id;
    card.className = `vocab-dict-card ${isCurrent ? "current-item" : ""}`;

    const header = document.createElement("div");
    header.className = "vocab-dict-header";

    const meaning = document.createElement("span");
    meaning.className = "vocab-dict-meaning";
    meaning.textContent = item.answer;

    const badge = document.createElement("span");
    badge.className = `vocab-dict-badge ${isCurrent ? "badge-current" : "badge-other"}`;
    badge.textContent = isCurrent ? "현재 문제" : "다른 쓰임";

    header.appendChild(meaning);
    header.appendChild(badge);

    const sentence = document.createElement("p");
    sentence.className = "vocab-dict-sentence";
    sentence.innerHTML = renderQuestionSentence(item);

    const sentenceKo = document.createElement("p");
    sentenceKo.className = "vocab-dict-sentence-ko";
    sentenceKo.textContent = item.sentenceKo || "해석 없음";

    card.appendChild(header);
    card.appendChild(sentence);
    card.appendChild(sentenceKo);
    list.appendChild(card);
  });

  container.appendChild(list);
  els.vocabDictionaryContainer.appendChild(container);
}

// 단어 상세조회 모달 열기 함수
function openWordDetailModal(termKey) {
  if (!els.wordDetailDialog || !els.dialogWordTitle || !els.dialogWordBody) return;

  const related = getRelatedVocabItems(termKey);
  if (!related.length) return;

  els.dialogWordTitle.textContent = related[0].term;
  els.dialogWordBody.innerHTML = "";

  // 1. 뜻 뱃지 모음
  const meaningsTitle = document.createElement("div");
  meaningsTitle.className = "dialog-section-title";
  meaningsTitle.textContent = "대표 뜻 목록";
  els.dialogWordBody.appendChild(meaningsTitle);

  const badgeWrap = document.createElement("div");
  badgeWrap.className = "dialog-meanings-badge-wrap";
  
  const uniqueMeanings = [...new Set(related.map(item => item.answer))];
  uniqueMeanings.forEach(meaning => {
    const badge = document.createElement("span");
    badge.className = "dialog-meaning-badge";
    badge.textContent = meaning;
    badgeWrap.appendChild(badge);
  });
  els.dialogWordBody.appendChild(badgeWrap);

  // 2. 예문 문맥 리스트
  const sentencesTitle = document.createElement("div");
  sentencesTitle.className = "dialog-section-title";
  sentencesTitle.textContent = "학습 예문 및 설명";
  els.dialogWordBody.appendChild(sentencesTitle);

  related.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "dialog-sentence-card";

    const en = document.createElement("p");
    en.className = "en";
    en.innerHTML = `${index + 1}. ${renderQuestionSentence(item)}`;

    const ko = document.createElement("p");
    ko.className = "ko";
    ko.textContent = item.sentenceKo || "해석 없음";

    card.appendChild(en);
    card.appendChild(ko);

    if (item.grammarNote) {
      const note = document.createElement("div");
      note.className = "note";
      note.innerHTML = `💡 ${formatExplanationHtml(item.grammarNote)}`;
      card.appendChild(note);
    }

    els.dialogWordBody.appendChild(card);
  });

  els.wordDetailDialog.showModal();
}

// 모달 닫기
function closeWordDetailModal() {
  if (els.wordDetailDialog) {
    els.wordDetailDialog.close();
  }
}

// 힌트 토글 로직
function toggleHint() {
  if (!state.current || !els.hintContentPanel || !els.hintToggleButton) return;

  const isHidden = els.hintContentPanel.classList.contains("hidden");
  if (isHidden) {
    const item = state.current;
    let hintText = "";

    if (item.questionType === "meaning") {
      const posMap = {
        noun: "명사",
        verb: "동사",
        adjective: "형용사",
        adverb: "부사",
        conjunction: "접속사",
        preposition: "전치사",
        tense: "시제/동사"
      };
      const pos = posMap[item.grammarFocus] || item.grammarFocus || "어휘";
      hintText = `이 단어의 품사는 [<strong>${pos}</strong>] 입니다.`;
    } else {
      hintText = `정답 어휘의 한국어 뜻은 [<strong>${item.term}</strong>] 입니다.`;
    }

    els.hintContentPanel.innerHTML = hintText;
    els.hintContentPanel.classList.remove("hidden");
    els.hintToggleButton.textContent = "💡 힌트 닫기";
  } else {
    els.hintContentPanel.classList.add("hidden");
    els.hintContentPanel.textContent = "";
    els.hintToggleButton.textContent = "💡 힌트 보기";
  }
}

async function loadInitialDataset() {
  state.dataset = await Storage.loadDataset();
  return state.dataset.items.length ? "데이터 불러오기 완료" : "데이터 없음";
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

async function loadProgress() {
  const saved = await Storage.loadProgress();
  if (saved?.version && saved.itemStats && Array.isArray(saved.attempts)) {
    state.progress = {
      ...state.progress,
      ...saved,
      dailyGoal: saved.dailyGoal ?? 30,
      dailyCompleted: saved.dailyCompleted ?? 0,
      streak: saved.streak ?? 0,
      lastActiveDate: saved.lastActiveDate ?? null,
      activeDates: saved.activeDates ?? [],
      lastResetDate: saved.lastResetDate ?? null,
    };
  }
  checkDailyReset();
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
  let activePool = pool;
  if (state.current && pool.length > 1) {
    activePool = pool.filter((item) => item.id !== state.current.id);
  }
  if (!activePool.length) return null;
  const sorted = [...activePool].sort((a, b) => weightedScore(b) - weightedScore(a));
  const limit = Math.max(5, Math.min(sorted.length, Math.ceil(sorted.length * 0.1)));
  const randomIndex = Math.floor(Math.random() * limit);
  return sorted[randomIndex];
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

function isExcludeMasteredActive() {
  return els.excludeMasteredCheckbox && els.excludeMasteredCheckbox.checked;
}

function modeItems(items = filteredItems()) {
  let pool = items;
  if (state.mode === "weak") pool = items.filter(isWeakItem);
  else if (state.mode === "new") pool = items.filter(isNewItem);
  else if (state.mode === "paragraph") {
    pool = items.filter((item) => item.contextType === "paragraph" || item.sentence.length > 180);
  }
  else if (state.mode === "mixed") {
    const byId = new Map();
    items.filter(isWeakItem).forEach((item) => byId.set(item.id, item));
    items.filter(isNewItem).forEach((item) => byId.set(item.id, item));
    pool = byId.size ? Array.from(byId.values()) : items;
  }
  
  if (isExcludeMasteredActive()) {
    const filtered = pool.filter(item => !isMasteredStats(existingItemStats(item.id)));
    if (filtered.length > 0) {
      return filtered;
    }
  }
  return pool;
}

function pickNextItem() {
  const items = filteredItems();
  if (!items.length) return null;
  if (state.mode === "all") {
    let pool = items;
    if (isExcludeMasteredActive()) {
      const filtered = pool.filter(item => !isMasteredStats(existingItemStats(item.id)));
      if (filtered.length > 0) pool = filtered;
    }
    return pool[Math.floor(Math.random() * pool.length)];
  }

  let pool = modeItems(items);
  if (state.mode === "mixed") {
    pool = todayPool(items);
  }
  if (state.mode === "paragraph") {
    const paragraphs = items.filter((item) => item.contextType === "paragraph" || item.sentence.length > 180);
    pool = paragraphs.length ? paragraphs : items;
  }

  if (isExcludeMasteredActive()) {
    const filteredPool = pool.filter(item => !isMasteredStats(existingItemStats(item.id)));
    if (filteredPool.length > 0) {
      pool = filteredPool;
    }
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
  if (els.vocabDictionaryContainer) els.vocabDictionaryContainer.innerHTML = "";
  if (els.hintContentPanel && els.hintToggleButton) {
    els.hintContentPanel.classList.add("hidden");
    els.hintContentPanel.textContent = "";
    els.hintToggleButton.textContent = "💡 힌트 보기";
  }
  els.questionSource.textContent = item.source;
  els.questionTags.textContent = [QUESTION_TYPES[item.questionType], item.quality, ...item.tags].filter(Boolean).join(" · ");
  els.questionSentence.classList.toggle("paragraph", item.contextType === "paragraph" || item.sentence.length > 180);
  els.questionSentence.innerHTML = renderQuestionSentence(item);
  els.questionPrompt.textContent = item.prompt;
  els.currentTerm.textContent = currentItemLabel(item);
  els.answerText.textContent = item.answer;
  els.blankSentence.textContent = answerSentenceLine(item);
  els.sentenceKo.textContent = item.sentenceKo || "문장 해석 데이터 없음";
  els.grammarNote.innerHTML = item.grammarNote ? formatExplanationHtml(item.grammarNote) : "문법 포인트 데이터 없음";

  els.choices.innerHTML = "";
  const prefixes = ["(A) ", "(B) ", "(C) ", "(D) "];
  item.choices.forEach((choice, index) => {
    const button = document.createElement("button");
    button.className = "choice-button";
    button.type = "button";
    button.textContent = `${prefixes[index] || ""}${choice}`;
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
  
  // 오늘 진도 증가 및 스트릭 업데이트
  state.progress.dailyCompleted += 1;
  updateStreak();
  saveProgress();

  if (!correct && els.questionCard) {
    els.questionCard.classList.add("shake-card");
    setTimeout(() => {
      els.questionCard.classList.remove("shake-card");
    }, 400);
  }

  $$(".choice-button").forEach((button, choiceIndex) => {
    if (choiceIndex === item.answerIndex) button.classList.add("correct");
    if (choiceIndex === index && !correct) button.classList.add("wrong");
  });
  els.answerPanel.classList.remove("hidden");
  renderVocabDictionary(item);
  updateSelfCheckButtons();
  renderAll();
}

function nextQuestion() {
  if (state.practiceStarted && state.progress.dailyCompleted >= state.progress.dailyGoal) {
    showSuccessCard();
    return;
  }
  
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
  if (els.successCard) {
    els.successCard.classList.add("hidden");
  }
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
  const items = state.dataset.items;
  const total = items.length;
  const unseenCount = items.filter(isNewItem).length;
  const weakCount = items.filter(isWeakItem).length;
  const masteredCount = items.filter(item => isMasteredStats(existingItemStats(item.id))).length;
  
  // 마스터 단어 배제 상태일 때 실제 풀 수 있는 문제 수 계산
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

  if (els.homeTotal) els.homeTotal.textContent = String(total);
  if (els.homeUnseen) els.homeUnseen.textContent = String(unseenCount);
  if (els.homeMastered) els.homeMastered.textContent = String(masteredCount);
  if (els.homeWeak) els.homeWeak.textContent = String(weakCount);

  const learnedCount = total - unseenCount;
  const progressPct = total ? Math.round((learnedCount / total) * 100) : 0;
  
  let summaryText = "";
  if (total === 0) {
    summaryText = "자료 탭에서 study-items.approved.json을 로드하십시오.";
  } else if (learnedCount === 0) {
    summaryText = `🔥 토익 정복의 첫걸음! 전체 ${total}개 문제 중 아직 학습한 문제가 없습니다. '오늘 학습 시작'으로 출발하세요!`;
  } else {
    const excludeVal = els.excludeMasteredCheckbox?.checked;
    const filterNote = excludeVal ? " (마스터 제외)" : "";
    summaryText = `🔥 현재 전체 문제 중 <strong>${learnedCount}개(${progressPct}%)</strong>를 건드렸고, <strong>${masteredCount}개</strong>를 완벽히 마스터했습니다! 약점 ${weakCount}개를 극복 중이며, ${modeLabel}${filterNote} 모드에서 대기 중인 문제는 ${activeCount}개입니다.`;
  }
  
  if (els.homeSummary) els.homeSummary.innerHTML = summaryText;
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
    tr.addEventListener("click", () => openWordDetailModal(row.term));
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
    || (stats.seen > 0 && accuracy < 0.75);
}

function isMasteredStats(stats) {
  if (!stats) return false;
  const accuracy = stats.seen ? stats.correct / stats.seen : 0;
  return stats.seen >= 3 && accuracy >= 0.9 && (stats.streak || 0) >= 3;
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

function getKstDateString() {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const date = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${date}`;
}

function checkDailyReset() {
  const todayStr = getKstDateString();
  if (state.progress.lastResetDate !== todayStr) {
    state.progress.dailyCompleted = 0;
    state.progress.lastResetDate = todayStr;
    saveProgress();
  }
  
  // 스트릭 끊김 감지
  const lastActive = state.progress.lastActiveDate;
  if (lastActive) {
    const today = new Date(todayStr);
    const lastDate = new Date(lastActive);
    const diffTime = Math.abs(today - lastDate);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays > 1 && lastActive !== todayStr) {
      state.progress.streak = 0;
      saveProgress();
    }
  }
}

function updateStreak() {
  const todayStr = getKstDateString();
  const lastActive = state.progress.lastActiveDate;
  
  if (!state.progress.activeDates) {
    state.progress.activeDates = [];
  }
  if (!state.progress.activeDates.includes(todayStr)) {
    state.progress.activeDates.push(todayStr);
  }
  
  if (lastActive !== todayStr) {
    if (lastActive) {
      const today = new Date(todayStr);
      const lastDate = new Date(lastActive);
      const diffTime = Math.abs(today - lastDate);
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      
      if (diffDays === 1) {
        state.progress.streak += 1;
      } else {
        state.progress.streak = 1;
      }
    } else {
      state.progress.streak = 1;
    }
    state.progress.lastActiveDate = todayStr;
  }
}

function renderProgressBar() {
  const completed = state.progress.dailyCompleted;
  const goal = state.progress.dailyGoal;
  const pctValue = goal > 0 ? Math.min(100, (completed / goal) * 100) : 0;
  
  if (els.progressBarFill) {
    els.progressBarFill.style.width = `${pctValue}%`;
  }
  if (els.progressText) {
    els.progressText.textContent = `${completed} / ${goal}`;
  }
}

function showSuccessCard() {
  if (els.questionCard) els.questionCard.classList.add("hidden");
  if (els.successCard) els.successCard.classList.remove("hidden");
  
  if (els.successSolved) els.successSolved.textContent = `${state.progress.dailyGoal}문제`;
  
  const todayStr = getKstDateString();
  const todayAttempts = state.progress.attempts.filter(a => a.at.startsWith(todayStr));
  const correctCount = todayAttempts.filter(a => a.correct).length;
  const accuracyPct = todayAttempts.length ? pct(correctCount / todayAttempts.length) : "0%";
  
  if (els.successAccuracy) els.successAccuracy.textContent = accuracyPct;
  if (els.successStreak) els.successStreak.textContent = `${state.progress.streak}일`;
}

function continueStudy() {
  state.progress.dailyGoal += 10;
  saveProgress();
  if (els.successCard) els.successCard.classList.add("hidden");
  nextQuestion();
}

function renderStreakCalendar() {
  if (!els.streakCalendar) return;
  els.streakCalendar.innerHTML = "";
  
  const today = new Date();
  const dates = [];
  for (let i = 27; i >= 0; i--) {
    const d = new Date();
    d.setDate(today.getDate() - i);
    dates.push(d);
  }
  
  dates.forEach(d => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const date = String(d.getDate()).padStart(2, '0');
    const dateStr = `${year}-${month}-${date}`;
    
    const dayEl = document.createElement("div");
    dayEl.className = "calendar-day";
    dayEl.textContent = d.getDate();
    
    if (dateStr === getKstDateString()) {
      dayEl.classList.add("today");
    }
    
    if (state.progress.activeDates && state.progress.activeDates.includes(dateStr)) {
      dayEl.classList.add("active");
      dayEl.title = "학습 완료!";
    }
    
    els.streakCalendar.appendChild(dayEl);
  });
}

function renderStreakWidget() {
  if (els.streakCount) {
    els.streakCount.textContent = `${state.progress.streak}일째`;
  }
  if (els.dailyGoalSelect) {
    els.dailyGoalSelect.value = String(state.progress.dailyGoal);
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
  renderProgressBar();
  renderStreakCalendar();
  renderStreakWidget();
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

// 가상 전체화면 상태 변수 (iframe/GAS 전체화면 차단 시 폴백용)
let isVirtualFullscreen = false;

function fullscreenElement() {
  if (isVirtualFullscreen) return els.appShell;
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

function fullscreenSupported() {
  return true; // 가상 전체화면을 상시 지원하므로 항상 true
}

async function enterFullscreen() {
  const root = document.documentElement;
  // GAS 웹앱(iframe) 환경이거나 상단 프레임과 다를 경우 곧바로 가상 전체화면 사용
  if (isGas || window.self !== window.top) {
    toggleVirtualFullscreen(true);
    return;
  }

  const request = root.requestFullscreen || root.webkitRequestFullscreen;
  if (!request) {
    toggleVirtualFullscreen(true);
    return;
  }

  try {
    await request.call(root);
  } catch (err) {
    console.warn("Browser fullscreen request rejected, using virtual fullscreen.", err);
    toggleVirtualFullscreen(true);
  }
}

async function exitFullscreen() {
  if (isVirtualFullscreen) {
    toggleVirtualFullscreen(false);
    return;
  }
  const exit = document.exitFullscreen || document.webkitExitFullscreen;
  if (!exit) {
    toggleVirtualFullscreen(false);
    return;
  }
  try {
    await exit.call(document);
  } catch {
    toggleVirtualFullscreen(false);
  }
}

function toggleVirtualFullscreen(force) {
  if (!els.appShell) return;
  if (force !== undefined) {
    isVirtualFullscreen = force;
  } else {
    isVirtualFullscreen = !isVirtualFullscreen;
  }
  if (isVirtualFullscreen) {
    els.appShell.classList.add("virtual-fullscreen");
  } else {
    els.appShell.classList.remove("virtual-fullscreen");
  }
  updateFullscreenButton();
}

function updateFullscreenButton() {
  if (!els.fullscreenButton || !els.fullscreenIcon) return;
  const active = Boolean(fullscreenElement());
  els.fullscreenButton.setAttribute("aria-pressed", active ? "true" : "false");
  els.fullscreenButton.setAttribute("aria-label", active ? "전체화면 해제" : "전체화면");
  els.fullscreenButton.title = active ? "전체화면 해제" : "전체화면";
  els.fullscreenIcon.textContent = active ? "×" : "⛶";
}

async function toggleFullscreen() {
  try {
    if (fullscreenElement()) {
      await exitFullscreen();
    } else {
      await enterFullscreen();
    }
  } catch {
    toggleVirtualFullscreen();
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
      // 탭 전환 시 보류 중인 저장을 즉시 완료(Flush)
      if (hasPendingSave) {
        saveProgress(true);
      }
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
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) {
      isVirtualFullscreen = false;
    }
    updateFullscreenButton();
  });
  document.addEventListener("webkitfullscreenchange", () => {
    if (!document.webkitFullscreenElement) {
      isVirtualFullscreen = false;
    }
    updateFullscreenButton();
  });
  updateFullscreenButton();
  els.weakSearch.addEventListener("input", renderWeakTable);
  $("#exportDatasetButton").addEventListener("click", () => downloadJson("toeic-study-items.json", state.dataset));
  $("#exportProgressButton").addEventListener("click", () => downloadJson("toeic-study-progress.json", state.progress));
  els.exportWeakButton?.addEventListener("click", () => downloadJson("toeic-study-weak-words.json", weakExportData()));
  $("#resetProgressButton").addEventListener("click", resetProgress);
  els.dailyGoalSelect?.addEventListener("change", (e) => {
    state.progress.dailyGoal = parseInt(e.target.value, 10);
    saveProgress();
    renderAll();
  });
  els.excludeMasteredCheckbox?.addEventListener("change", (e) => {
    localStorage.setItem("toeic-study.exclude-mastered", e.target.checked ? "true" : "false");
    renderAll();
  });
  els.successHomeButton?.addEventListener("click", showPracticeHome);
  els.successContinueButton?.addEventListener("click", continueStudy);

  if (els.hintToggleButton) {
    els.hintToggleButton.addEventListener("click", toggleHint);
  }

  if (els.dialogCloseButton) {
    els.dialogCloseButton.addEventListener("click", closeWordDetailModal);
  }

  if (els.wordDetailDialog) {
    els.wordDetailDialog.addEventListener("click", (event) => {
      const rect = els.wordDetailDialog.getBoundingClientRect();
      const isInDialog = (rect.top <= event.clientY && event.clientY <= rect.top + rect.height
        && rect.left <= event.clientX && event.clientX <= rect.left + rect.width);
      if (!isInDialog) {
        closeWordDetailModal();
      }
    });
  }

  if (els.currentTerm) {
    els.currentTerm.addEventListener("click", () => {
      if (state.current) {
        openWordDetailModal(state.current.termKey);
      }
    });
  }

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

  els.gasDatasetInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const raw = await readJsonFile(file);
    const normalized = normalizeDataset(raw);
    if (!isStudyReadyDataset(normalized)) {
      alert("이 파일은 완성 학습 데이터가 아닙니다. sentenceKo, grammarNote, quality=approved가 있는 검증 데이터만 업로드할 수 있습니다.");
      event.target.value = "";
      return;
    }
    
    if (!confirm(`스프레드시트에 있는 기존 단어 데이터를 모두 지우고, 새로 올리시겠습니까? (총 ${normalized.items.length}개 단어)`)) {
      event.target.value = "";
      return;
    }

    showSyncLoader("구글 시트에 단어 데이터를 업로드하는 중...");
    try {
      const res = await GAS.call("seedDatasetFromJson", JSON.stringify(normalized));
      if (res.success) {
        alert(`🎉 구글 시트 단어장 시딩 완료! 총 ${res.count}개의 단어가 스프레드시트에 기입되었습니다.`);
        await DBStore.set(DATASET_KEY, normalized); // 로컬 캐시 동시 저장!
        state.dataset = normalized;
        renderAll();
        showPracticeHome();
      }
    } catch (e) {
      alert(`업로드 중 오류 발생: ${e.message}`);
    } finally {
      hideSyncLoader();
      event.target.value = "";
    }
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
    saveProgress(true); // 수동 입력 데이터는 즉시 플러시
    renderAll();
    renderCurrent();
    event.target.value = "";
  });

  // 브라우저 닫기/이동 시 미저장 데이터 강제 플러시
  window.addEventListener("beforeunload", () => {
    if (hasPendingSave) {
      saveProgress(true);
    }
  });
}

async function init() {
  bindEvents();
  if (els.excludeMasteredCheckbox) {
    els.excludeMasteredCheckbox.checked = localStorage.getItem("toeic-study.exclude-mastered") === "true";
  }
  await loadProgress();
  await loadInitialDataset();
  showPracticeHome();
  renderCurrent();
  renderAll();
}

init();
