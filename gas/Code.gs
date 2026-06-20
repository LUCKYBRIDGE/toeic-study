/**
 * TOEIC Study Web App - Apps Script Backend
 * 
 * 구글 스프레드시트를 데이터베이스로 활용하여 다중 사용자 학습 진도 및 단어장 데이터를 관리합니다.
 */

// 상수 정의
const DB_SHEETS = {
  ITEMS: "study-items",
  PROGRESS: "progress-records"
};

// study-items 시트의 컬럼 헤더 매핑
const ITEM_FIELDS = [
  "id", "term", "termKey", "contextId", "questionType", "answer",
  "choices", "answerIndex", "tags", "source", "sentence",
  "contextType", "blankSentence", "sentenceKo", "grammarFocus",
  "grammarNote", "quality", "prompt"
];

/**
 * 웹 애플리케이션 진입점 (HTTP GET)
 */
function doGet() {
  return HtmlService.createTemplateFromFile("index")
    .evaluate()
    .setTitle("TOEIC Voca Study")
    .addMetaTag("viewport", "width=device-width, initial-scale=1.0")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/**
 * 스프레드시트 인스턴스 획득 및 데이터베이스 탭 초기화
 */
function getSpreadsheet() {
  let ss = null;
  try {
    ss = SpreadsheetApp.getActiveSpreadsheet();
  } catch (e) {
    // getActiveSpreadsheet 실패 시 openById 폴백
  }
  
  if (!ss) {
    const SPREADSHEET_ID = "1CjdvXRo-R2si9yF0nZujFMciPWRRDV6k8QffzbhqnO8"; 
    if (SPREADSHEET_ID) {
      try {
        ss = SpreadsheetApp.openById(SPREADSHEET_ID);
      } catch (e) {
        Logger.log("openById failed: " + e.toString());
      }
    }
  }

  if (!ss) {
    throw new Error("Active spreadsheet not found. SPREADSHEET_ID가 올바르고 권한이 부여되었는지 확인해 주세요.");
  }
  
  // 1. study-items 시트 확인 및 생성
  let itemsSheet = ss.getSheetByName(DB_SHEETS.ITEMS);
  if (!itemsSheet) {
    itemsSheet = ss.insertSheet(DB_SHEETS.ITEMS);
    itemsSheet.appendRow(ITEM_FIELDS);
    itemsSheet.getRange(1, 1, 1, ITEM_FIELDS.length).setFontWeight("bold").setBackground("#f3f3f3");
    itemsSheet.setFrozenRows(1);
  }

  // 2. progress-records 시트 확인 및 생성
  let progressSheet = ss.getSheetByName(DB_SHEETS.PROGRESS);
  if (!progressSheet) {
    progressSheet = ss.insertSheet(DB_SHEETS.PROGRESS);
    const headers = ["email", "progressJson", "updatedAt"];
    progressSheet.appendRow(headers);
    progressSheet.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#f3f3f3");
    progressSheet.setFrozenRows(1);
  }

  return ss;
}

/**
 * 전체 단어 학습 데이터셋 가져오기
 */
function getStudyDataset() {
  try {
    const ss = getSpreadsheet();
    const sheet = ss.getSheetByName(DB_SHEETS.ITEMS);
    const lastRow = sheet.getLastRow();
    
    if (lastRow <= 1) {
      return { version: 1, stats: { itemCount: 0 }, items: [] };
    }

    const data = sheet.getRange(2, 1, lastRow - 1, ITEM_FIELDS.length).getValues();
    const items = data.map(row => {
      const item = {};
      ITEM_FIELDS.forEach((field, index) => {
        let val = row[index];
        if ((field === "choices" || field === "tags") && typeof val === "string") {
          try {
            val = JSON.parse(val);
          } catch (e) {
            val = val ? val.split(",").map(s => s.trim()) : [];
          }
        }
        if (field === "answerIndex") {
          val = Number.isInteger(val) ? val : parseInt(val, 10) || 0;
        }
        item[field] = val;
      });
      return item;
    });

    return {
      version: 1,
      stats: { itemCount: items.length },
      items: items
    };
  } catch (error) {
    Logger.log("getStudyDataset error: " + error.toString());
    throw new Error("학습 데이터를 가져오는 중 오류가 발생했습니다: " + error.message);
  }
}

/**
 * 현재 사용자의 이메일 기반 진행 데이터 조회
 */
function getUserProgress() {
  const email = Session.getActiveUser().getEmail();
  if (!email) {
    return { guest: true };
  }

  try {
    const ss = getSpreadsheet();
    const sheet = ss.getSheetByName(DB_SHEETS.PROGRESS);
    const lastRow = sheet.getLastRow();
    
    if (lastRow <= 1) {
      return { email: email, progress: null };
    }

    const data = sheet.getRange(2, 1, lastRow - 1, 3).getValues();
    for (let i = 0; i < data.length; i++) {
      if (data[i][0] === email) {
        const progressJson = data[i][1];
        try {
          return {
            email: email,
            progress: JSON.parse(progressJson)
          };
        } catch (e) {
          Logger.log("JSON Parse error for user " + email);
          return { email: email, progress: null, error: "JSON_PARSE_ERROR" };
        }
      }
    }
    
    return { email: email, progress: null };
  } catch (error) {
    Logger.log("getUserProgress error: " + error.toString());
    throw new Error("진행 정보를 조회하는 중 오류가 발생했습니다: " + error.message);
  }
}

/**
 * 현재 사용자의 진행 데이터 저장 (트랜잭션 락 적용)
 */
function saveUserProgress(progressJson) {
  const email = Session.getActiveUser().getEmail();
  if (!email) {
    return { success: false, message: "로그인된 구글 사용자 이메일을 가져올 수 없습니다. 권한 설정을 확인하세요." };
  }

  try {
    JSON.parse(progressJson);
  } catch (e) {
    return { success: false, message: "올바르지 않은 JSON 데이터 형식입니다." };
  }

  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (e) {
    return { success: false, message: "구글 시트의 쓰기 작업이 밀려 처리에 실패했습니다. 잠시 후 다시 시도해 주세요." };
  }

  try {
    const ss = getSpreadsheet();
    const sheet = ss.getSheetByName(DB_SHEETS.PROGRESS);
    const lastRow = sheet.getLastRow();
    const now = new Date();

    let userRowIndex = -1;
    if (lastRow > 1) {
      const emails = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (let i = 0; i < emails.length; i++) {
        if (emails[i][0] === email) {
          userRowIndex = i + 2;
          break;
        }
      }
    }

    if (userRowIndex !== -1) {
      sheet.getRange(userRowIndex, 2, 1, 2).setValues([[progressJson, now]]);
    } else {
      sheet.appendRow([email, progressJson, now]);
    }

    return { success: true, email: email, updatedAt: now.toISOString() };
  } catch (error) {
    Logger.log("saveUserProgress error: " + error.toString());
    return { success: false, message: error.message };
  } finally {
    lock.releaseLock();
  }
}

/**
 * [관리자용 유틸리티] 로컬 JSON 파일을 구글 시트의 study-items에 한 번에 시딩(Seeding)하기 위한 함수
 */
function seedDatasetFromJson(jsonString) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(15000);
  } catch (e) {
    throw new Error("동시 쓰기 락 획득 실패. 시딩 작업을 진행할 수 없습니다.");
  }

  try {
    const data = JSON.parse(jsonString);
    const items = Array.isArray(data?.items) ? data.items : [];
    if (!items.length) {
      throw new Error("시딩할 단어 데이터가 비어있거나 올바르지 않은 포맷입니다.");
    }

    const ss = getSpreadsheet();
    const sheet = ss.getSheetByName(DB_SHEETS.ITEMS);
    
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      sheet.deleteRows(2, lastRow - 1);
    }

    const rows = items.map(item => {
      return ITEM_FIELDS.map(field => {
        let val = item[field];
        if (val === undefined || val === null) {
          val = "";
        }
        if (field === "choices" || field === "tags") {
          val = JSON.stringify(val);
        }
        return val;
      });
    });

    sheet.getRange(2, 1, rows.length, ITEM_FIELDS.length).setValues(rows);
    return { success: true, count: rows.length };
  } catch (error) {
    Logger.log("seedDatasetFromJson error: " + error.toString());
    throw new Error("시딩 처리 중 오류가 발생했습니다: " + error.message);
  } finally {
    lock.releaseLock();
  }
}
