#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "private-data" / "generated"
APPROVED_FILE = GENERATED_DIR / "study-items.approved.json"
LEXICON_APPROVED_FILE = GENERATED_DIR / "study-items.lexicon-approved.json"
NUMBERED_VOCAB_PDFS = sorted(ROOT.glob("materials/[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]*.pdf"))

ONLINE_QUESTION_PDF = ROOT / "materials/ets-online-rc/RC (온라인 테스트 및 단어장 파일)/ETS 토익 정기시험 기출종합서 RC 온라인 모의고사_문제지.pdf"
ONLINE_ANSWER_PDF = ROOT / "materials/ets-online-rc/RC (온라인 테스트 및 단어장 파일)/ETS 토익 정기시험 기출종합서 RC 온라인 모의고사_정답 및 번역.pdf"
STARTER_QUESTION_PDF = ROOT / "materials/ets-starter-rc/ETS Starter RC_TEST, VOCA(PDF)/RC_TEST_QUESTIONS.pdf"
STARTER_ANSWER_PDF = ROOT / "materials/ets-starter-rc/ETS Starter RC_TEST, VOCA(PDF)/RC_TEST_ANSWERS.pdf"
OFFICIAL_SAMPLE_PDF = ROOT / "materials/00-official-reference/toeic-listening-reading-sample-test.pdf"
YBM_BASIC_PART5_PDF = ROOT / "materials/ybm-basic-grammar/YBM TOEIC Basic Grammar/YBM 토익 기초영문법-PART 5 실전 모의고사.pdf"

QUESTION_NUM_RE = re.compile(r"^(1[0-2][0-9]|130)\.\s*(.*)$")
ANSWER_KEY_RE = re.compile(r"\b(1[0-2][0-9]|130)\s+\(([A-D])\)")
OPTION_RE = re.compile(r"^\(([A-D])\)\s*(.+)$")
HANGUL_RE = re.compile(r"[가-힣]")
EN_RE = re.compile(r"[A-Za-z]")
TARGET_RE = re.compile(r"-{3,}")
NUMBERED_VOCAB_ENTRY_RE = re.compile(r"^\s*(\d{1,4})\s+(.+?)\s+\1\s+(.*)$")
NUMBER_ONLY_RE = re.compile(r"^\s*(\d{1,4})\s*$")
NUMBERED_DEFINITION_RE = re.compile(r"^(\d{1,4})\s+(.*)$")

NUMBERED_VOCAB_TERM_OVERRIDES = {
    # The source PDFs visibly pair these terms with the wrong headword.
    # Teach the meaning-compatible TOEIC word instead of preserving the typo.
    615: "accord",
    645: "contribute",
    # pypdf splits this visible headword across three lines: accommodation / s.
    683: "accommodations",
}

NUMBERED_VOCAB_NOISE = (
    "단어를 클릭하면",
    "예문과 용법",
    "https://",
    "온라인 토익 단어장",
)

CONJUNCTIONS = {
    "and",
    "after",
    "although",
    "as",
    "because",
    "before",
    "but",
    "considering",
    "even if",
    "if",
    "nor",
    "now that",
    "once",
    "or",
    "so",
    "unless",
    "until",
    "when",
    "whenever",
    "whether",
    "while",
}

PREPOSITIONS = {
    "across",
    "among",
    "as a result of",
    "as",
    "at",
    "between",
    "by",
    "during",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "onto",
    "prior to",
    "through",
    "throughout",
    "to",
    "under",
    "within",
    "with",
}

QUESTION_TYPE_OVERRIDES = {
    ("part5-online-rc", 109): "word",
    ("part5-online-rc", 117): "word",
    ("part5-online-rc", 121): "word",
    ("part5-online-rc", 127): "word",
    ("part5-starter-rc", 102): "word",
}

YBM_BASIC_TRANSLATION_OVERRIDES = {
    ("part5-ybm-basic-1", 119): "잠재 직원들은 누가 가장 적합한지를 결정하기 위해 여러 차례 면접을 본다.",
}

OFFICIAL_SAMPLE_QUESTIONS = {
    101: {
        "stem": "Customer reviews indicate that many modern mobile devices are often unnecessarily -------.",
        "choices": {"A": "complication", "B": "complicates", "C": "complicate", "D": "complicated"},
    },
    102: {
        "stem": "Jamal Nawzad has received top performance reviews ------- he joined the sales department two years ago.",
        "choices": {"A": "despite", "B": "except", "C": "since", "D": "during"},
    },
    103: {
        "stem": "Gyeon Corporation’s continuing education policy states that ------- learning new skills enhances creativity and focus.",
        "choices": {"A": "regular", "B": "regularity", "C": "regulate", "D": "regularly"},
    },
    104: {
        "stem": "Among ------- recognized at the company awards ceremony were senior business analyst Natalie Obi and sales associate Peter Comeau.",
        "choices": {"A": "who", "B": "whose", "C": "they", "D": "those"},
    },
    105: {
        "stem": "All clothing sold in Develyn’s Boutique is made from natural materials and contains no ------- dyes.",
        "choices": {"A": "immediate", "B": "synthetic", "C": "reasonable", "D": "assumed"},
    },
}

OFFICIAL_SAMPLE_ANSWER_KEY = {
    101: "D",
    102: "C",
    103: "D",
    104: "D",
    105: "B",
}

OFFICIAL_SAMPLE_TRANSLATIONS = {
    101: "고객 후기는 많은 현대 모바일 기기들이 종종 불필요하게 복잡하다는 것을 보여 준다.",
    102: "자말 나우자드는 2년 전 영업부에 합류한 이후 최고의 성과 평가를 받아 왔다.",
    103: "계온사의 계속 교육 정책은 정기적으로 새로운 기술을 배우는 것이 창의성과 집중력을 높인다고 명시한다.",
    104: "회사 시상식에서 인정받은 사람들 중에는 수석 비즈니스 분석가 나탈리 오비와 영업 사원 피터 코모가 있었다.",
    105: "데블린 부티크에서 판매되는 모든 의류는 천연 소재로 만들어지며 합성 염료를 포함하지 않는다.",
}

PART5_EXPLANATIONS = {
    ("part5-online-rc", 101): (
        "빈칸은 소유격 his와 명사 design 사이에서 명사를 꾸미는 형용사 자리입니다.",
        "creates는 동사, creating은 분사/동명사, creatively는 부사라서 design 앞의 형용사 역할을 할 수 없습니다.",
    ),
    ("part5-online-rc", 102): (
        "could 뒤에는 동사원형이 필요하고, 문맥상 LED 조명이 사무실의 비용을 절약한다는 의미가 되어야 합니다.",
        "take, simplify, improve도 동사원형이지만 '사무실에 연간 수백 달러를 절약해 주다'라는 목적어 money와 가장 자연스럽게 결합하는 동사는 save입니다.",
    ),
    ("part5-online-rc", 103): (
        "has transitioned라는 동사구를 꾸미는 부사 자리입니다.",
        "smooth는 형용사, smoothing은 분사/동명사, smoothness는 명사이므로 동사구 transitioned를 직접 수식할 수 없습니다.",
    ),
    ("part5-online-rc", 104): (
        "8 a.m.라는 마감 시각 앞에서 '~까지'를 뜻하는 전치사가 필요합니다.",
        "across는 범위, under는 아래/조건, within은 기간 안을 뜻하지만 정확한 마감 시각에는 by가 가장 자연스럽습니다.",
    ),
    ("part5-online-rc", 105): (
        "marketing team의 lunch outing을 대신하는 소유대명사 자리입니다.",
        "they는 주격, them은 목적격, themselves는 재귀대명사라서 scheduled의 목적어로 '그들의 것'이라는 의미를 만들 수 없습니다.",
    ),
    ("part5-online-rc", 106): (
        "was 뒤 주격 보어 자리에서 사람의 상태를 설명하는 형용사가 필요하고, 문맥상 '운이 좋았다'가 자연스럽습니다.",
        "talented, common, beneficial은 문법적으로 형용사일 수 있지만 '미술관 가까이에서 자라다'라는 이유와 가장 잘 맞는 의미는 fortunate입니다.",
    ),
    ("part5-online-rc", 107): (
        "주어 Members는 복수이고, by the company’s shareholders가 있어 수동태가 필요합니다.",
        "have elected는 능동태라 주어가 선출하는 의미가 되고, is elected는 수 일치가 맞지 않으며, elected만 쓰면 완전한 동사가 되지 않습니다.",
    ),
    ("part5-online-rc", 108): (
        "빈칸 뒤에 주어 any renovation work와 동사 can begin이 이어지므로 절을 연결하는 접속사가 필요합니다.",
        "prior to와 of는 뒤에 명사구가 와야 하고, ever는 부사라 절을 연결하지 못합니다.",
    ),
    ("part5-online-rc", 109): (
        "all of our 뒤에는 met의 목적어가 되는 복수 명사가 필요합니다.",
        "requires는 동사, requiring은 분사, required는 과거분사/형용사라서 all of our 뒤의 명사 자리를 채울 수 없습니다.",
    ),
    ("part5-online-rc", 110): (
        "비교급 higher를 강조하는 부사가 필요합니다. 비교급 앞에서는 much가 '훨씬'이라는 의미로 자연스럽습니다.",
        "more는 higher와 중복되고, very와 so는 일반 형용사/부사를 강조할 수 있지만 비교급 higher 앞의 표준 강조어가 아닙니다.",
    ),
    ("part5-online-rc", 111): (
        "24 hours가 반복 주기를 나타내므로 '매 24시간마다'라는 표현이 필요합니다.",
        "whenever는 절을 이끌어야 하고, less와 even은 24 hours 앞에서 반복 주기를 만들지 못합니다.",
    ),
    ("part5-online-rc", 112): (
        "small 뒤, of calls 앞에는 양을 나타내는 명사가 필요합니다. volume of calls는 '전화량'이라는 자연스러운 결합입니다.",
        "content, setting, process는 calls와 함께 '전화량'이라는 의미를 만들지 못합니다.",
    ),
    ("part5-online-rc", 113): (
        "문장의 주어 자리이며 of paper currency가 뒤에서 수식하므로 명사 production이 필요합니다.",
        "products는 생산품, produce는 동사/농산물, produced는 과거분사라서 '지폐 생산'이라는 명사구를 만들 수 없습니다.",
    ),
    ("part5-online-rc", 114): (
        "specify 뒤에 '누구에게 연락해야 하는지'라는 의미가 필요하고, to contact의 목적어 역할을 하는 의문대명사가 들어가야 합니다.",
        "how는 방법, that은 명사절 접속사, whose는 소유격이라 contact의 목적어가 될 수 없습니다.",
    ),
    ("part5-online-rc", 115): (
        "Western Europe이라는 지역 명사구 앞에서 서비스 범위를 나타내는 전치사가 필요합니다.",
        "among은 복수 집단 사이, onto는 이동 방향, as는 자격/역할을 뜻하므로 '서유럽 전역'이라는 의미에는 throughout가 맞습니다.",
    ),
    ("part5-online-rc", 116): (
        "is not 뒤에서 보어로 쓰여 '권장되지 않는다'라는 수동 의미를 만드는 과거분사가 필요합니다.",
        "recommendation은 명사, recommending은 현재분사/동명사, recommend는 동사원형이라 be동사 뒤 보어로 이 문맥에 맞지 않습니다.",
    ),
    ("part5-online-rc", 117): (
        "attribute A to B는 'A를 B의 덕분으로 돌리다'라는 표현입니다. her reelection과 to the popularity가 이 구조를 만듭니다.",
        "accomplished, predicted, regarded는 뒤의 to와 결합해 같은 의미 구조를 만들지 못합니다.",
    ),
    ("part5-online-rc", 118): (
        "앞 절의 상황이 이미 성립했기 때문에 뒤 절의 결과가 가능해졌다는 의미입니다. Now that은 '~이므로, 이제 ~이기 때문에'를 뜻합니다.",
        "So that은 목적, Due to와 Rather than은 뒤에 절이 아니라 명사구나 동명사구가 와야 합니다.",
    ),
    ("part5-online-rc", 119): (
        "damage를 앞에서 꾸미며 '지속적인 피해'라는 의미를 만드는 형용사가 필요합니다.",
        "last는 동사/형용사로 이 자리의 의미가 어색하고, lastly와 lastingly는 부사라 damage를 직접 꾸밀 수 없습니다.",
    ),
    ("part5-online-rc", 120): (
        "because of his 뒤에는 이유가 되는 명사가 필요하고, reputation for는 '~로 명성이 있음'이라는 표현입니다.",
        "knowledge, approach, performance도 명사지만 for effective recruiting과 결합해 '영입으로 정평이 난' 의미를 가장 정확히 만드는 것은 reputation입니다.",
    ),
    ("part5-online-rc", 121): (
        "complaint 뒤에서 '불만 처리 절차'라는 복합명사를 만드는 복수 명사가 필요합니다.",
        "proceeding은 진행/절차의 단수적 의미, procedural은 형용사, proceeds는 수익이라는 뜻이라 complaint procedures와 맞지 않습니다.",
    ),
    ("part5-online-rc", 122): (
        "less likely라는 비교 표현을 정도상 크게 강조하는 부사가 필요합니다. markedly는 '현저하게'라는 뜻입니다.",
        "forcefully는 강제로, alternatively는 대안적으로, respectively는 각각이라는 뜻이라 통계 감소의 정도를 나타내지 못합니다.",
    ),
    ("part5-online-rc", 123): (
        "주어 앞에서 범위를 제한해 '가장 흥미로운 질문들만'이라는 의미를 만드는 제한 부사가 필요합니다.",
        "After와 Considering은 문장 구조상 어색하고, Neither는 nor와 함께 쓰여야 합니다.",
    ),
    ("part5-online-rc", 124): (
        "in need of replacement 앞에서 필요 정도를 강조하는 부사가 필요합니다. critically in need of는 '절실히 필요한'이라는 의미입니다.",
        "criticized는 과거분사, critical은 형용사, criticism은 명사라 in need of를 자연스럽게 수식하지 못합니다.",
    ),
    ("part5-online-rc", 125): (
        "territory를 꾸미며 '방대한 지역'이라는 의미를 만드는 형용사가 필요합니다.",
        "deliberate, resolute, adept는 각각 고의적인/단호한/능숙한이라는 뜻이라 territory의 크기와 맞지 않습니다.",
    ),
    ("part5-online-rc", 126): (
        "a pair 안의 두 신발 중 하나와 나머지 하나를 비교하므로 the other가 필요합니다.",
        "another는 불특정한 다른 하나, one another는 상호 관계, other one은 관사와 지시가 부족해 이 문맥의 '나머지 한 짝'을 정확히 나타내지 못합니다.",
    ),
    ("part5-online-rc", 127): (
        "goals of all stakeholders are 뒤에는 목표들이 서로 맞춰져 있다는 상태를 나타내는 형용사/분사형이 필요합니다.",
        "adhered는 adhere to가 필요하고, corresponded는 correspond to/with, collaborated는 collaborate with가 필요해 빈칸 뒤 구조와 맞지 않습니다.",
    ),
    ("part5-online-rc", 128): (
        "require that 절에서는 동사원형을 쓰는 구조가 나오며, badges는 착용되는 대상이므로 수동 의미가 필요합니다.",
        "worn만으로는 동사가 완성되지 않고, to wear는 능동 부정사, have been worn은 require that 구조의 원형 조건과 맞지 않습니다.",
    ),
    ("part5-online-rc", 129): (
        "sturdy 뒤에서 형용사를 보충해 '~할 만큼 충분히 튼튼한'이라는 enough to 구조를 만듭니다.",
        "exactly, alike, beyond은 sturdy 뒤에서 to handle과 연결되는 정도 표현을 만들지 못합니다.",
    ),
    ("part5-online-rc", 130): (
        "characterized by the 뒤에는 명사가 필요하고, incorporation of A into B는 'A를 B에 통합함'이라는 표현입니다.",
        "improvement, perception, excess는 everyday noises into the music과 결합해 '음악에 접목'이라는 의미를 만들지 못합니다.",
    ),
    ("part5-starter-rc", 101): (
        "be similar to는 '~와 비슷하다'라는 고정 표현입니다. too 뒤에서 정도가 지나침을 나타냅니다.",
        "recent, lengthy, simple은 형용사지만 뒤의 to her previous books와 자연스럽게 결합하지 않습니다.",
    ),
    ("part5-starter-rc", 102): (
        "requires의 목적어 자리이고 thorough의 수식을 받으므로 명사가 필요합니다.",
        "to analyze와 analyze는 동사 형태, analyzed는 과거분사라 thorough 뒤의 명사 자리를 채울 수 없습니다.",
    ),
    ("part5-starter-rc", 103): (
        "restarting the program과 your computer itself를 병렬로 연결해야 하므로 and가 필요합니다.",
        "but은 대조, so는 결과, while은 절을 이끄는 접속사라 두 목적어를 단순 병렬로 연결하지 못합니다.",
    ),
    ("part5-starter-rc", 104): (
        "removed라는 동사를 꾸미는 부사 자리입니다. quietly removed는 '조용히 철수시켰다'라는 의미입니다.",
        "quiet는 형용사, quieted는 동사 과거형, quietness는 명사라 removed를 수식할 수 없습니다.",
    ),
    ("part5-starter-rc", 105): (
        "주어 The reporter와 사진을 찍은 사람이 같으므로 재귀대명사 himself가 필요합니다.",
        "he는 주격, him은 목적격이지만 강조/재귀 의미가 없고, his own은 뒤에 명사가 필요합니다.",
    ),
    ("part5-starter-rc", 106): (
        "must 뒤에는 동사원형이 오며, that절의 내용을 '증명하다'가 문맥상 가장 자연스럽습니다.",
        "request, secure, authorize는 비자 신청 맥락에서 가능한 단어지만 '가족 구성원임을 증명하다'라는 that절 목적어와 맞지 않습니다.",
    ),
    ("part5-starter-rc", 107): (
        "judging committee는 '심사위원회'라는 자연스러운 복합명사입니다.",
        "decision, order, expert는 made up of scientists와 연결되어 조직을 가리키는 명사로 쓰이기 어렵습니다.",
    ),
    ("part5-starter-rc", 108): (
        "remain 뒤에서 상태를 나타내는 형용사 보어가 필요합니다. separate는 '분리된 상태의'라는 형용사입니다.",
        "separating은 능동 진행 의미, separation은 명사, separately는 부사라 remain의 보어로 적절하지 않습니다.",
    ),
    ("part5-starter-rc", 109): (
        "between A and B는 두 범위 사이를 나타내는 고정 구조입니다. 뒤에 and five가 있어 between이 필요합니다.",
        "around, over, from은 three and five business days와 함께 정확한 범위 구조를 만들지 못합니다.",
    ),
    ("part5-starter-rc", 110): (
        "replacement를 꾸미며 임시가 아닌 '영구적인 후임자'라는 의미가 필요합니다.",
        "comfortable, spacious, gradual은 사람/직책의 후임자라는 명사와 의미상 어울리지 않습니다.",
    ),
    ("part5-starter-rc", 111): (
        "비교급 easier를 강조하는 부사 자리입니다. 비교급 앞에서는 much가 '훨씬'이라는 의미로 쓰입니다.",
        "well, very, so는 이 문맥에서 비교급 easier를 자연스럽게 강조하지 못합니다.",
    ),
    ("part5-starter-rc", 112): (
        "주어는 Downloading all of the necessary software programs라는 동명사구로 단수 취급합니다.",
        "take는 수 일치가 맞지 않고, are taken은 수동태, taking은 완전한 동사가 아니므로 takes가 필요합니다.",
    ),
    ("part5-starter-rc", 113): (
        "are 뒤 보어 자리에서 devices의 상태를 설명하는 형용사가 필요합니다.",
        "complicate와 complicates는 동사, complication은 명사라 be동사 뒤의 형용사 보어가 될 수 없습니다.",
    ),
    ("part5-starter-rc", 114): (
        "full이라는 형용사를 꾸미는 부사 자리입니다. completely full은 '완전히 가득 찬'이라는 의미입니다.",
        "completion은 명사, completed는 과거분사/형용사, complete는 형용사라 full을 수식하지 못합니다.",
    ),
    ("part5-starter-rc", 115): (
        "there has been growing 뒤에는 단수 명사 demand가 와서 '수요가 증가하고 있다'라는 의미를 만듭니다.",
        "demands는 복수라 has been과 어색하고, demanded와 demandingly는 각각 분사/부사라 명사 자리에 맞지 않습니다.",
    ),
    ("part5-starter-rc", 116): (
        "fulfill obligations는 '의무를 이행하다'라는 토익 빈출 결합입니다.",
        "expire는 만료되다, comply는 보통 comply with가 필요하며, undergo는 겪다라는 뜻이라 obligations와 맞지 않습니다.",
    ),
    ("part5-starter-rc", 117): (
        "the only contestant 뒤에서 명사를 수식하는 to부정사가 필요합니다. the only + 명사 + to V 구조입니다.",
        "answerer는 사람 명사, answers는 동사/복수명사, answered는 과거분사라 '대답한 유일한 참가자' 구조를 만들지 못합니다.",
    ),
    ("part5-starter-rc", 118): (
        "앞 절은 할인 혜택이 매력적이라는 내용이고 뒤 절은 6개월 후에만 가능하다는 제한이므로 양보 접속사가 필요합니다.",
        "rather than은 비교/선택, in spite of는 전치사구를 이끌고, whether는 '~인지 아닌지'라 대조 의미가 맞지 않습니다.",
    ),
    ("part5-starter-rc", 119): (
        "working environment는 '근무 환경'이라는 자연스러운 결합입니다.",
        "equipment, preference, knowledge는 safe working과 결합해 직원에게 제공하는 환경이라는 의미를 만들지 못합니다.",
    ),
    ("part5-starter-rc", 120): (
        "make A mandatory for B는 'A를 B에게 의무화하다'라는 구조입니다.",
        "dedicated, capable, alert는 형용사지만 wearing a helmet의 법적 의무 여부를 나타내지 못합니다.",
    ),
    ("part5-starter-rc", 121): (
        "either A or B는 둘 중 하나를 연결하는 상관접속사 구조입니다.",
        "nor는 neither와 함께, neither와 both는 뒤 구조와 맞지 않아 either Tokyo와 연결할 수 없습니다.",
    ),
    ("part5-starter-rc", 122): (
        "packaging을 꾸미며 장거리 식품 운송에 필요한 '보호용 포장'이라는 의미가 필요합니다.",
        "expired, assumed, mutual은 packaging과 결합해 운송 보호 목적을 나타내지 못합니다.",
    ),
    ("part5-starter-rc", 123): (
        "determine a device’s location을 꾸며 위치를 얼마나 정확히 파악하는지 나타내는 부사가 필요합니다.",
        "highly, patiently, severely는 위치 파악의 정확도를 나타내는 부사로 어울리지 않습니다.",
    ),
    ("part5-starter-rc", 124): (
        "앞 절 전체 결과로 뒤의 some frequent customers to complain이 이어지므로 현재분사 causing이 필요합니다.",
        "cause와 causes는 완전한 동사라 연결 구조가 맞지 않고, caused는 수동/과거 의미라 결과 분사구와 맞지 않습니다.",
    ),
    ("part5-starter-rc", 125): (
        "persistent rainfall이 수위 상승의 원인이므로 '~의 결과로'를 뜻하는 전치사구가 필요합니다.",
        "depending on은 ~에 따라, according to는 ~에 따르면, with the exception of는 ~을 제외하고라 원인 의미가 아닙니다.",
    ),
    ("part5-starter-rc", 126): (
        "by the time we arrive가 미래 기준 시점을 만들고, 그때 이미 시작되어 있을 일을 말하므로 미래완료가 필요합니다.",
        "had started는 과거완료, starting과 having started는 완전한 동사가 아니므로 주절의 동사 자리에 맞지 않습니다.",
    ),
    ("part5-starter-rc", 127): (
        "mark the northern boundary of는 '~의 북쪽 경계를 표시하다'라는 자연스러운 표현입니다.",
        "scope, feature, proportion은 theater district의 북쪽 한계를 나타내는 명사로 맞지 않습니다.",
    ),
    ("part5-starter-rc", 128): (
        "The 뒤, of the support columns 앞에는 명사구가 필요하며, 보강 작업이라는 행위를 나타내는 동명사 strengthening이 자연스럽습니다.",
        "strong은 형용사, strength는 힘/강도, strengthen은 동사라 of the support columns와 함께 작업명을 만들기 어렵습니다.",
    ),
    ("part5-starter-rc", 129): (
        "뒤에 완전한 절 there are more than 500...가 오며, 주 행사장 사용 조건을 나타내야 하므로 if가 필요합니다.",
        "despite는 전치사, either는 or와 함께 쓰이고, that은 조건 의미를 만들지 못합니다.",
    ),
    ("part5-starter-rc", 130): (
        "coincide with는 '~와 동시에 일어나다, 일치하다'라는 고정 표현입니다.",
        "introduce, complement, endorse는 with the hundredth anniversary와 결합해 전시회 개막 시점이 기념일과 맞물린다는 의미를 만들지 못합니다.",
    ),
}

STARTER_TRANSLATIONS = {
    101: "평론가들은 유 씨의 새 소설이 이전 책들과 너무 비슷하다고 말한다.",
    102: "좋은 보안 시스템을 선택하려면 보호될 시설에 대한 철저한 분석이 필요하다.",
    103: "정보기술부에 연락하기 전에 항상 프로그램과 컴퓨터 자체를 다시 시작해 보세요.",
    104: "브러스터 푸즈는 저염 스낵 판매가 감소한 후 그 제품들을 매장에서 조용히 철수시켰다.",
    105: "사진사가 제시간에 도착하지 않을 것이 분명해지자 기자는 직접 몇 장의 사진을 찍었다.",
    106: "이 비자를 받으려면 신청자들은 자신들이 시민권자의 가족 구성원임을 증명해야 한다.",
    107: "마레스상 심사위원회는 다양한 전문 분야의 과학자들로 구성되어 있다.",
    108: "합병에도 불구하고 두 회사의 경영진은 당분간 분리된 상태로 남아 있을 것이다.",
    109: "주문의 예상 배송 기간은 영업일 기준 3일에서 5일 사이이다.",
    110: "다니엘 싱클레어는 영구 후임자가 채용될 때까지 소사 씨의 직책을 맡을 것이다.",
    111: "두 등산로 모두 아름다운 전망을 제공하지만, 파인 트레일이 오크 트레일보다 훨씬 더 쉽다.",
    112: "빠른 인터넷 연결이 있어도 필요한 모든 소프트웨어 프로그램을 다운로드하는 데 거의 5분이 걸린다.",
    113: "고객 후기들은 많은 현대 스마트 기기들이 종종 불필요하게 복잡하다는 것을 보여 준다.",
    114: "에너지 낭비를 피하려면 식기세척기가 더러운 접시로 완전히 찰 때까지 작동하지 마세요.",
    115: "그 아파트 단지가 지어진 이후, 그 지역에서 대중교통 확대에 대한 수요가 증가하고 있다.",
    116: "우리가 계약상 의무를 이행하지 않으면 큰 금전적 벌금을 물게 될 것이다.",
    117: "이번 주 퀴즈 게임 에피소드에서 한 교사가 마지막 문제에 정확히 대답한 유일한 참가자였다.",
    118: "직원 할인은 매력적인 혜택이지만, 근무 6개월 후에만 이용할 수 있다.",
    119: "창고는 직원들에게 안전한 근무 환경을 제공하기 위해 노력해야 한다.",
    120: "제안된 조례는 시내 모든 자전거 이용자에게 헬멧 착용을 의무화할 것이다.",
    121: "합격자들은 내년 말까지 도쿄나 샌프란시스코 중 한 곳에 배치될 것이다.",
    122: "A.F.사는 식품의 장거리 운송을 위한 보호 포장을 전문으로 한다.",
    123: "“Find My Fone” 앱은 기기의 위치를 더 정확하게 파악할 수 있게 되면 더 유용해질 것이다.",
    124: "코미어 슈퍼마켓은 10월에 매장 배치를 바꾸어 일부 단골 고객들이 불만을 제기하게 했다.",
    125: "지난주 계속된 강우로 인해 프렌티스 호수의 수위가 6인치 상승했다.",
    126: "우리가 회의장에 도착할 때쯤 우드워스 씨의 연설은 시작되어 있을 것이다.",
    127: "빅포드 스트리트는 극장가의 북쪽 경계를 표시하는 것으로 널리 여겨진다.",
    128: "설리번 다리 아래 지지 기둥 보강 작업은 카운티의 기반 시설 예산 대부분을 소진할 것이다.",
    129: "와탄 이벤트는 사전 등록 참석자가 500명을 넘을 경우 주 행사장을 사용한다.",
    130: "“A Century in Easley” 전시회 개막은 그 마을 창립 100주년과 일치할 것이다.",
}


def normalize_space(value: str) -> str:
    value = value.replace("a.m .", "a.m.").replace("p.m .", "p.m.")
    value = re.sub(r"([A-Za-z])- ([A-Za-z])", r"\1-\2", value)
    return re.sub(r"\s+", " ", value).strip()


def read_pages(path: Path, page_indexes: range) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    parts = []
    for index in page_indexes:
        if index < len(reader.pages):
            parts.append(reader.pages[index].extract_text() or "")
    return "\n".join(parts)


def read_page(path: Path, page_index: int, *, layout: bool = False) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    if page_index >= len(reader.pages):
        return ""
    if layout:
        return reader.pages[page_index].extract_text(extraction_mode="layout") or ""
    return reader.pages[page_index].extract_text() or ""


def parse_question_blocks(path: Path, page_indexes: range) -> dict[int, dict]:
    text = read_pages(path, page_indexes)
    blocks: dict[int, list[str]] = {}
    current: int | None = None

    for raw_line in text.splitlines():
        line = normalize_space(raw_line)
        if line.upper() == "PART 6":
            break
        if not line or line.isdigit() or line.startswith("GO ON TO THE NEXT PAGE"):
            continue
        match = QUESTION_NUM_RE.match(line)
        if match:
            current = int(match.group(1))
            blocks[current] = [match.group(2)]
            continue
        if current is not None:
            blocks[current].append(line)

    parsed: dict[int, dict] = {}
    for number, lines in blocks.items():
        stem_lines: list[str] = []
        choices: dict[str, str] = {}
        current_choice: str | None = None
        for line in lines:
            option = OPTION_RE.match(line)
            if option:
                current_choice = option.group(1)
                choices[current_choice] = normalize_space(option.group(2))
            elif current_choice:
                choices[current_choice] = normalize_space(f"{choices[current_choice]} {line}")
            else:
                stem_lines.append(line)

        stem = normalize_space(" ".join(stem_lines))
        if len(choices) == 4 and TARGET_RE.search(stem):
            parsed[number] = {"stem": stem, "choices": choices}
    return parsed


def parse_question_lines(lines: list[str]) -> dict[int, dict]:
    blocks: dict[int, list[str]] = {}
    current: int | None = None

    for raw_line in lines:
        line = normalize_space(raw_line)
        if (
            not line
            or line.isdigit()
            or line.startswith("Unauthorized copying")
            or line.startswith("READING TEST")
            or line.startswith("Directions:")
            or line.startswith("In the Reading test")
            or line.startswith("You must mark")
            or line.startswith("PART 5")
            or "제한시간" in line
        ):
            continue
        match = QUESTION_NUM_RE.match(line)
        if match:
            current = int(match.group(1))
            blocks[current] = [match.group(2)]
            continue
        if current is not None:
            blocks[current].append(line)

    parsed: dict[int, dict] = {}
    for number, block_lines in blocks.items():
        stem_lines: list[str] = []
        choices: dict[str, str] = {}
        current_choice: str | None = None
        for line in block_lines:
            option = OPTION_RE.match(line)
            if option:
                current_choice = option.group(1)
                choices[current_choice] = normalize_space(option.group(2))
            elif current_choice:
                choices[current_choice] = normalize_space(f"{choices[current_choice]} {line}")
            else:
                stem_lines.append(line)

        stem = normalize_space(" ".join(stem_lines))
        if len(choices) == 4 and TARGET_RE.search(stem):
            parsed[number] = {"stem": stem, "choices": choices}
    return parsed


def parse_two_column_layout_question_blocks(path: Path, page_indexes: range, *, split_at: int = 73) -> dict[int, dict]:
    parsed: dict[int, dict] = {}
    for page_index in page_indexes:
        left_lines: list[str] = []
        right_lines: list[str] = []
        for line in read_page(path, page_index, layout=True).splitlines():
            left_lines.append(line[:split_at])
            right_lines.append(line[split_at:])
        parsed.update(parse_question_lines(left_lines))
        parsed.update(parse_question_lines(right_lines))
    return parsed


def parse_answer_key(path: Path, page_indexes: range) -> dict[int, str]:
    text = read_pages(path, page_indexes)
    return {int(number): letter for number, letter in ANSWER_KEY_RE.findall(text)}


def looks_like_vocab_line(line: str) -> bool:
    if not HANGUL_RE.search(line):
        return True
    if re.match(r"^[a-z][A-Za-z -]*\s+[가-힣]", line):
        return True
    english_terms = re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", line)
    return len(english_terms) >= 3 and not re.match(r"^[가-힣]", line)


def clean_translation(lines: list[str]) -> str:
    kept: list[str] = []
    for raw_line in lines:
        line = normalize_space(raw_line)
        if not line or line.isdigit() or line.upper() == "PART 5":
            continue
        if looks_like_vocab_line(line):
            break
        kept.append(line)
    return normalize_space(" ".join(kept))


def parse_translations(path: Path, page_indexes: range) -> dict[int, str]:
    text = read_pages(path, page_indexes)
    translations: dict[int, str] = {}
    current: int | None = None
    buffer: list[str] = []

    for raw_line in text.splitlines():
        line = normalize_space(raw_line)
        if re.fullmatch(r"1[0-2][0-9]|130", line):
            if current is not None:
                translations[current] = clean_translation(buffer)
            current = int(line)
            buffer = []
            continue
        if current is not None:
            buffer.append(line)

    if current is not None:
        translations[current] = clean_translation(buffer)
    return translations


def clean_korean_translation(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"\s+([.,;:!?])", r"\1", value)
    value = re.sub(r"(\d+)\s+(개|명|월|일|인분|인당|개월|달러|시간)", r"\1\2", value)
    value = re.sub(r"([A-Z])\s*-\s*(\d)", r"\1-\2", value)
    value = value.replace("‘ ", "‘").replace(" ’", "’")
    value = value.replace("“ ", "“").replace(" ”", "”")
    value = re.sub(r"([’”])\s+([은는이가을를와과에의도만로])", r"\1\2", value)
    value = value.replace("< ", "<").replace(" >", ">")
    value = value.replace("[ ", "[").replace(" ]", "]")
    value = value.replace("( ", "(").replace(" )", ")")
    return value.strip()


def parse_numbered_answer_translations(path: Path, page_indexes: range) -> dict[int, str]:
    translations: dict[int, str] = {}
    current: int | None = None
    capturing = False
    buffer: list[str] = []

    def flush() -> None:
        if current is not None and buffer:
            translations[current] = clean_korean_translation(" ".join(buffer))

    for raw_line in read_pages(path, page_indexes).splitlines():
        line = normalize_space(raw_line)
        number_match = re.fullmatch(r"1[0-2][0-9]|130", line)
        if number_match:
            flush()
            current = int(line)
            capturing = False
            buffer = []
            continue
        if current is None:
            continue
        if line == "해석":
            capturing = True
            buffer = []
            continue
        if line == "어휘" or line == "ANSWERS" or line.startswith("PART 5"):
            if capturing:
                flush()
            capturing = False
            buffer = []
            continue
        if capturing and line:
            buffer.append(line)

    flush()
    return translations


def infer_question_type(answer: str, stem: str, choices: list[str]) -> str:
    lower = answer.lower()
    after_blank = TARGET_RE.split(stem, maxsplit=1)[1] if TARGET_RE.search(stem) else ""
    after_words = re.findall(r"[A-Za-z]+", after_blank)
    if lower in CONJUNCTIONS and len(after_words) >= 2:
        return "conjunction"
    if lower in PREPOSITIONS:
        return "preposition"
    if is_verb_form_set(choices):
        return "tense"
    return "word"


def is_verb_form_set(choices: list[str]) -> bool:
    joined = " ".join(choice.lower() for choice in choices)
    auxiliaries = (" is ", " are ", " was ", " were ", " has ", " have ", " had ", " will ", " be ", " been ")
    if any(aux in f" {joined} " for aux in auxiliaries):
        return True
    if any(choice.lower().startswith("to ") for choice in choices):
        return True
    return sum(choice.lower().endswith(("ed", "ing", "s")) for choice in choices) >= 3


def answer_letter(choices: list[str], answer: str) -> str:
    try:
        return "ABCD"[choices.index(answer)]
    except ValueError:
        return "?"


def toeic_tip(question_type: str) -> str:
    if question_type == "conjunction":
        return "빈칸 뒤가 절인지 명사구인지 먼저 확인하면 접속사와 전치사를 빠르게 구분할 수 있습니다."
    if question_type == "preposition":
        return "전치사는 뒤 명사구와 앞 문장 사이의 시간, 범위, 원인, 마감 관계를 잡는 것이 핵심입니다."
    if question_type == "tense":
        return "주어 수, 능동/수동, 시제 단서, 준동사 구조를 순서대로 확인하세요."
    return "Part 5 어휘 문제는 빈칸 앞뒤의 품사 자리와 자주 함께 쓰이는 collocation을 먼저 확인하세요."


def part5_grammar_note(source_id: str, number: int, question_type: str, answer: str, choices: list[str]) -> str:
    reason, wrongs = PART5_EXPLANATIONS.get((source_id, number), grammar_note(question_type, answer))
    letter = answer_letter(choices, answer)
    return (
        f"해설 | {reason} 따라서 정답은 ({letter}) {answer}입니다.\n"
        f"오답 포인트 | {wrongs}\n"
        f"토익 포인트 | {toeic_tip(question_type)}"
    )


def vocab_tip(term: str, answer: str, usage: str) -> str:
    lower = term.lower()
    if " " in lower:
        return f"{term}는 여러 단어가 한 의미 단위로 쓰이는 표현입니다. 문제에서는 단어별 직역보다 전체 뜻 '{answer}'로 빠르게 잡아야 합니다."
    if usage in {"verb", "verb-phrase"} or answer.endswith("하다") or "하다," in answer:
        return f"{term}는 동사/동사 표현으로 출제될 가능성이 큽니다. 뒤에 어떤 목적어가 오는지 함께 외우면 Part 5 어휘 문제에서 도움이 됩니다."
    if usage == "adverb" or answer.endswith(("게", "히")):
        return f"{term}는 동사나 형용사를 꾸며 정도와 방식을 나타내는 부사로 자주 쓰입니다."
    if usage == "adjective" or answer.endswith(("한", "적인", "있는", "없는")):
        return f"{term}는 명사 앞에서 성질을 설명하는 형용사로 자주 출제됩니다."
    return f"{term}는 토익 문서, 업무, 공지 문맥에서 명사로 자주 확인해야 하는 기본 어휘입니다."


def vocab_grammar_note(term: str, answer: str, usage: str) -> str:
    return (
        f"어휘 해설 | {term}의 뜻은 '{answer}'입니다. 선택지는 모두 승인된 원본 어휘 목록에서 가져온 뜻이지만, 이 단어와 직접 연결되는 뜻은 하나뿐입니다.\n"
        f"토익 포인트 | {vocab_tip(term, answer, usage)}\n"
        "오답 포인트 | 뜻 고르기 문제는 비슷해 보이는 한국어 선택지보다 영어 단어의 품사와 자주 쓰이는 문맥을 먼저 떠올리는 것이 안전합니다."
    )


def grammar_note(question_type: str, answer: str) -> tuple[str, str]:
    if question_type == "conjunction":
        return (
            "문장 앞뒤의 논리 관계를 보고 절을 연결하는 접속사가 필요합니다.",
            "다른 보기는 절 연결 구조나 의미 관계가 맞지 않습니다.",
        )
    if question_type == "preposition":
        return (
            "빈칸 뒤 명사구와 앞 문장 사이의 관계를 나타내는 전치사가 필요합니다.",
            "다른 보기는 시간, 범위, 방향, 원인 관계가 문맥과 맞지 않습니다.",
        )
    if question_type == "tense":
        return (
            "주어, 시점 표현, 수동태 여부를 함께 확인해야 하는 동사 형태 문제입니다.",
            "다른 보기는 수 일치, 태, 시제, 준동사 구조 중 하나가 맞지 않습니다.",
        )
    return (
        "문맥과 품사를 함께 보고 빈칸에 들어갈 어휘를 고르는 문제입니다.",
        "다른 보기는 품사나 collocation이 문맥과 맞지 않습니다.",
    )


def prompt_for(question_type: str) -> str:
    if question_type == "conjunction":
        return "빈칸에 들어갈 가장 알맞은 접속사는?"
    if question_type == "preposition":
        return "빈칸에 들어갈 가장 알맞은 전치사는?"
    if question_type == "tense":
        return "빈칸에 들어갈 가장 알맞은 동사 형태는?"
    return "빈칸에 들어갈 가장 알맞은 영단어는?"


def stable_id(*parts: str) -> str:
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def source_label(path: Path) -> str:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if len(parts) >= 3 and parts[0] == "materials":
        return f"{parts[1]} / {path.name}"
    return path.name


def clean_vocab_answer(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"\s+\d{1,3}$", "", value)
    return value.strip(" ,;/")


def valid_vocab_pair(term: str, answer: str) -> bool:
    if not term or not answer:
        return False
    if not HANGUL_RE.search(answer):
        return False
    if EN_RE.search(answer):
        return False
    if len(answer) > 42:
        return False
    return True


def stable_choices(answer: str, answers: list[str], seed: str) -> list[str]:
    pool = [candidate for candidate in dict.fromkeys(answers) if candidate != answer]
    start = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16) if pool else 0
    distractors: list[str] = []
    index = start
    while pool and len(distractors) < 3:
        candidate = pool[index % len(pool)]
        if candidate not in distractors:
            distractors.append(candidate)
        index += 17
    choices = [answer, *distractors]
    return sorted(choices, key=lambda choice: stable_id(seed, choice))


def numbered_vocab_line(raw_line: str) -> str:
    return normalize_space(raw_line.replace("\x00", " "))


def is_numbered_vocab_noise(line: str) -> bool:
    if not line:
        return True
    if any(noise in line for noise in NUMBERED_VOCAB_NOISE):
        return True
    if re.fullmatch(r"(?:\d\s*){1,4}", line):
        return True
    return False


def clean_numbered_term(number: int, value: str) -> str:
    if number in NUMBERED_VOCAB_TERM_OVERRIDES:
        return NUMBERED_VOCAB_TERM_OVERRIDES[number]
    value = normalize_space(value)
    if len(value.split()) > 1 and all(len(part) == 1 for part in value.split()):
        value = "".join(value.split())
    value = re.sub(r"[가-힣].*$", "", value)
    return value.strip(" ,;:/()[]")


def compact_korean_breaks(value: str) -> str:
    replacements = {
        "하 다": "하다",
        "되 다": "되다",
        "있 는": "있는",
        "없 는": "없는",
        "있 게": "있게",
        "없 게": "없게",
        "높 게": "높게",
        "낮 게": "낮게",
        "행 동": "행동",
        "수 단": "수단",
        "의미 있 게": "의미 있게",
        "다각화하 다": "다각화하다",
        "담 당자": "담당자",
        "유일무 이한": "유일무이한",
        "과장되지 않 은": "과장되지 않은",
    }
    for before, after in replacements.items():
        value = value.replace(before, after)
    return normalize_space(value)


def clean_numbered_meaning(raw_meaning: str) -> tuple[str, list[str]]:
    value = normalize_space(raw_meaning)
    value = re.sub(r"\b\d(?:\s+\d)+\b", "", value)
    value = re.sub(r"\([^)]*\)", " | ", value)
    value = re.sub(r"\b분사\b", " | ", value)
    value = re.sub(r"^1\s+", "", value)
    parts = []
    for part in value.split("|"):
        cleaned = compact_korean_breaks(part.strip(" ,.;"))
        if cleaned and HANGUL_RE.search(cleaned):
            parts.append(cleaned)
    primary = parts[0] if parts else ""
    return primary, parts


def parse_numbered_vocab_pdf(path: Path) -> list[dict]:
    text = read_pages(path, range(0, 20))
    lines = [numbered_vocab_line(line) for line in text.splitlines()]
    entries: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        number = int(current["number"])
        term = clean_numbered_term(number, current["term"])
        raw_meaning = normalize_space(" ".join(current["parts"]))
        meaning, meanings = clean_numbered_meaning(raw_meaning)
        if term and meaning:
            entries.append({
                "number": number,
                "term": term,
                "answer": meaning,
                "meanings": meanings,
                "rawMeaning": raw_meaning,
                "source": source_label(path),
                "sourcePath": str(path.relative_to(ROOT)),
            })
        current = None

    index = 0
    while index < len(lines):
        line = lines[index]
        entry = NUMBERED_VOCAB_ENTRY_RE.match(line)
        if entry:
            flush()
            current = {
                "number": int(entry.group(1)),
                "term": entry.group(2),
                "parts": [entry.group(3)],
            }
            index += 1
            continue

        number_only = NUMBER_ONLY_RE.match(line)
        if number_only:
            number = int(number_only.group(1))
            term_parts: list[str] = []
            lookahead = index + 1
            while lookahead < len(lines):
                definition = NUMBERED_DEFINITION_RE.match(lines[lookahead])
                if definition and int(definition.group(1)) == number:
                    flush()
                    current = {
                        "number": number,
                        "term": " ".join(term_parts),
                        "parts": [definition.group(2)],
                    }
                    index = lookahead + 1
                    break
                term_parts.append(lines[lookahead])
                lookahead += 1
            else:
                index += 1
            continue

        if current and not is_numbered_vocab_noise(line):
            current["parts"].append(line)
        index += 1

    flush()
    return entries


def load_numbered_vocab_entries() -> list[dict]:
    entries: list[dict] = []
    for path in NUMBERED_VOCAB_PDFS:
        entries.extend(parse_numbered_vocab_pdf(path))
    by_number = {entry["number"]: entry for entry in entries}
    missing = sorted(set(range(1, 1201)) - set(by_number))
    extra = sorted(number for number in by_number if number < 1 or number > 1200)
    if missing or extra or len(by_number) != 1200:
        raise ValueError(f"Expected numbered vocabulary 1-1200; missing={missing[:20]} extra={extra[:20]} count={len(by_number)}")
    return [by_number[number] for number in range(1, 1201)]


def numbered_vocab_tags(number: int) -> list[str]:
    band_start = ((number - 1) // 100) * 100 + 1
    band_end = band_start + 99
    return ["vocabulary", "numbered-voca", f"{band_start:04d}-{band_end:04d}"]


def numbered_vocab_note(entry: dict, direction: str) -> str:
    term = entry["term"]
    answer = entry["answer"]
    meanings = " / ".join(dict.fromkeys(entry.get("meanings") or [answer]))
    if direction == "term":
        return (
            f"어휘 해설 | '{answer}'에 해당하는 원본 단어장 표제어는 {term}입니다.\n"
            f"원본 뜻 | {meanings}\n"
            "오답 포인트 | 뜻을 보고 단어를 고를 때는 비슷한 한국어 의미보다 영어 철자와 품사를 함께 떠올리는 것이 중요합니다."
        )
    return (
        f"어휘 해설 | {term}의 대표 뜻은 '{answer}'입니다.\n"
        f"원본 뜻 | {meanings}\n"
        "오답 포인트 | 보기 중 단어와 바로 연결되는 뜻을 고르세요. 비슷한 뜻이 보여도 품사와 실제 사용 문맥이 맞는지 확인해야 합니다."
    )


def build_numbered_vocab_items() -> list[dict]:
    entries = load_numbered_vocab_entries()
    meanings = [entry["answer"] for entry in entries]
    terms = [entry["term"] for entry in entries]
    items: list[dict] = []

    for entry in entries:
        number = entry["number"]
        term = entry["term"]
        answer = entry["answer"]
        tags = numbered_vocab_tags(number)
        base = {
            "term": term,
            "termKey": normalize_space(term).lower(),
            "source": entry["source"],
            "sourcePath": entry["sourcePath"],
            "quality": "approved",
            "contextType": "vocabulary",
            "grammarFocus": "vocabulary",
            "tags": tags,
            "vocabNumber": number,
        }

        meaning_id = f"numbered-vocab-meaning-{number:04d}-{stable_id(term, answer)}"
        meaning_choices = stable_choices(answer, meanings, meaning_id)
        items.append({
            **base,
            "id": meaning_id,
            "questionType": "meaning",
            "contextId": f"numbered-vocab-{number:04d}",
            "answer": answer,
            "choices": meaning_choices,
            "answerIndex": meaning_choices.index(answer),
            "sentence": term,
            "sentenceKo": f"{term}: {answer}",
            "blankSentence": f"{term} = _____",
            "grammarNote": numbered_vocab_note(entry, "meaning"),
            "prompt": f"{number}번 단어 {term}의 뜻은?",
        })

        term_id = f"numbered-vocab-term-{number:04d}-{stable_id(answer, term)}"
        term_choices = stable_choices(term, terms, term_id)
        items.append({
            **base,
            "id": term_id,
            "questionType": "term",
            "contextId": f"numbered-vocab-{number:04d}",
            "answer": term,
            "choices": term_choices,
            "answerIndex": term_choices.index(term),
            "sentence": answer,
            "sentenceKo": f"{answer}: {term}",
            "blankSentence": f"{answer} = _____",
            "grammarNote": numbered_vocab_note(entry, "term"),
            "prompt": f"'{answer}'에 해당하는 영어 단어는?",
        })

    return items


def build_vocab_items() -> list[dict]:
    if not LEXICON_APPROVED_FILE.exists():
        return []
    data = json.loads(LEXICON_APPROVED_FILE.read_text(encoding="utf-8"))
    raw_items = data.get("items", [])
    vocab_entries = []
    seen: set[tuple[str, str]] = set()

    for item in raw_items:
        term = normalize_space(str(item.get("term", "")))
        answer = clean_vocab_answer(str(item.get("answer", "")))
        if not valid_vocab_pair(term, answer):
            continue
        key = (term.lower(), answer)
        if key in seen:
            continue
        seen.add(key)
        vocab_entries.append({**item, "term": term, "answer": answer})

    answers = [item["answer"] for item in vocab_entries]
    items = []
    for item in vocab_entries:
        term = item["term"]
        answer = item["answer"]
        source = normalize_space(str(item.get("source", "source vocabulary")))
        source_path = normalize_space(str(item.get("sourcePath", "")))
        item_id = f"vocab-{stable_id(source, term, answer)}"
        choices = stable_choices(answer, answers, item_id)
        tags = sorted((set(item.get("tags") or []) - {"approved"}) | {"vocabulary", "meaning"})
        items.append({
            "id": item_id,
            "questionType": "meaning",
            "term": term,
            "termKey": normalize_space(term).lower(),
            "contextId": f"vocab-{stable_id(source, term)}",
            "answer": answer,
            "choices": choices,
            "answerIndex": choices.index(answer),
            "tags": tags,
            "source": source,
            "sourcePath": source_path,
            "quality": "approved",
            "contextType": "vocabulary",
            "sentence": term,
            "sentenceKo": f"{term}: {answer}",
            "blankSentence": f"{term} = _____",
            "grammarFocus": "vocabulary-meaning",
            "grammarNote": vocab_grammar_note(term, answer, str(item.get("usage", ""))),
            "prompt": f"원본 어휘 자료에서 {term}의 뜻은?",
        })
    return items


def build_source_items(
    *,
    source_id: str,
    source_label: str,
    question_pdf: Path,
    answer_pdf: Path,
    question_pages: range,
    answer_key_pages: range,
    translations: dict[int, str],
) -> list[dict]:
    questions = parse_question_blocks(question_pdf, question_pages)
    answer_key = parse_answer_key(answer_pdf, answer_key_pages)
    return build_source_items_from_data(
        source_id=source_id,
        source_label=source_label,
        source_path=question_pdf,
        questions=questions,
        answer_key=answer_key,
        translations=translations,
    )


def build_source_items_from_data(
    *,
    source_id: str,
    source_label: str,
    source_path: Path,
    questions: dict[int, dict],
    answer_key: dict[int, str],
    translations: dict[int, str],
) -> list[dict]:
    items = []

    for number in range(101, 131):
        question = questions.get(number)
        letter = answer_key.get(number)
        sentence_ko = translations.get(number, "") or YBM_BASIC_TRANSLATION_OVERRIDES.get((source_id, number), "")
        if not question or not letter or not sentence_ko:
            continue

        choices_by_letter = question["choices"]
        answer = choices_by_letter[letter]
        choices = [choices_by_letter[key] for key in ("A", "B", "C", "D")]
        question_type = infer_question_type(answer, question["stem"], choices)
        question_type = QUESTION_TYPE_OVERRIDES.get((source_id, number), question_type)
        blank_sentence = TARGET_RE.sub("_____", question["stem"], count=1)
        sentence = TARGET_RE.sub(answer, question["stem"], count=1)
        tags = ["rc", "part5", question_type]

        items.append({
            "id": f"{source_id}-{number}-{stable_id(sentence, answer)}",
            "questionType": question_type,
            "term": answer,
            "termKey": normalize_space(answer).lower(),
            "contextId": f"{source_id}-{number}",
            "answer": answer,
            "choices": choices,
            "answerIndex": choices.index(answer),
            "tags": tags,
            "source": source_label,
            "sourcePath": str(source_path.relative_to(ROOT)),
            "quality": "approved",
            "contextType": "sentence",
            "sentence": sentence,
            "sentenceKo": sentence_ko,
            "blankSentence": blank_sentence,
            "grammarFocus": question_type,
            "grammarNote": part5_grammar_note(source_id, number, question_type, answer, choices),
            "prompt": prompt_for(question_type),
        })
    return items


def build_ybm_basic_part5_items() -> list[dict]:
    items: list[dict] = []
    for test_number, question_pages, answer_pages in (
        (1, range(1, 4), range(7, 11)),
        (2, range(4, 7), range(11, 15)),
    ):
        source_id = f"part5-ybm-basic-{test_number}"
        items.extend(build_source_items_from_data(
            source_id=source_id,
            source_label=f"ybm-basic-grammar Part 5 Test {test_number}",
            source_path=YBM_BASIC_PART5_PDF,
            questions=parse_two_column_layout_question_blocks(YBM_BASIC_PART5_PDF, question_pages),
            answer_key=parse_answer_key(YBM_BASIC_PART5_PDF, answer_pages),
            translations=parse_numbered_answer_translations(YBM_BASIC_PART5_PDF, answer_pages),
        ))
    return items


def build_official_sample_items() -> list[dict]:
    return build_source_items_from_data(
        source_id="part5-official-sample",
        source_label="ets-official-sample Part 5",
        source_path=OFFICIAL_SAMPLE_PDF,
        questions=OFFICIAL_SAMPLE_QUESTIONS,
        answer_key=OFFICIAL_SAMPLE_ANSWER_KEY,
        translations=OFFICIAL_SAMPLE_TRANSLATIONS,
    )


def build_items() -> list[dict]:
    items = []
    items.extend(build_numbered_vocab_items())
    items.extend(build_vocab_items())
    items.extend(build_source_items(
        source_id="part5-online-rc",
        source_label="ets-online-rc Part 5",
        question_pdf=ONLINE_QUESTION_PDF,
        answer_pdf=ONLINE_ANSWER_PDF,
        question_pages=range(0, 3),
        answer_key_pages=range(0, 1),
        translations=parse_translations(ONLINE_ANSWER_PDF, range(0, 4)),
    ))
    items.extend(build_source_items(
        source_id="part5-starter-rc",
        source_label="ets-starter-rc Part 5",
        question_pdf=STARTER_QUESTION_PDF,
        answer_pdf=STARTER_ANSWER_PDF,
        question_pages=range(0, 4),
        answer_key_pages=range(0, 1),
        translations=STARTER_TRANSLATIONS,
    ))
    items.extend(build_ybm_basic_part5_items())
    items.extend(build_official_sample_items())
    return items


def main() -> int:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    if APPROVED_FILE.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = APPROVED_FILE.with_suffix(f".backup-{timestamp}.json")
        shutil.copy2(APPROVED_FILE, backup)

    items = build_items()
    stats = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "itemCount": len(items),
        "sourceFileCount": len({item.get("sourcePath", "") for item in items if item.get("sourcePath")}),
        "source": "local private TOEIC Part 5 PDFs and approved source vocabulary",
        "sourceCounts": dict(Counter(item["source"] for item in items).most_common()),
        "questionTypeCounts": dict(Counter(item["questionType"] for item in items).most_common()),
        "tagCounts": dict(Counter(tag for item in items for tag in item["tags"]).most_common()),
    }
    APPROVED_FILE.write_text(
        json.dumps({"version": 1, "stats": stats, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(items)} approved study items to {APPROVED_FILE.relative_to(ROOT)}")
    print(f"Question type counts: {stats['questionTypeCounts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
