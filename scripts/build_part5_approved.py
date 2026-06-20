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
        return f"💡 **일타강사 실전 팁** | {term}은(는) 여러 단어가 결합하여 하나의 의미 덩어리를 이루는 다어구(collocation)입니다. 쪼개서 개별 단어로 외우지 말고, 하나의 단어처럼 '{answer}'로 입에 붙여 암기하는 것이 실전에서 0.5초 만에 답을 고르는 지름길입니다!"
    if usage in {"verb", "verb-phrase"} or answer.endswith("하다") or "하다," in answer:
        return f"💡 **일타강사 실전 팁** | {term}은(는) 문맥 속에서 주어의 행동이나 비즈니스 업무 처리를 완성하는 핵심 동사입니다. 동사 어휘는 항상 빈칸 뒤에 오는 목적어(명사구) 혹은 짝이 되는 전치사(자동사+전치사 구조)와의 궁합을 확인하는 연습을 하세요!"
    if usage == "adverb" or answer.endswith(("게", "히")):
        return f"💡 **일타강사 실전 팁** | {term}은(는) 문장의 동사나 형용사를 꾸며 의미를 더욱 풍부하게 만드는 수식어 부사입니다. 부사 문제는 수식 대상(주로 뒤의 p.p. 형태나 형용사, 동사)과의 자연스러운 번역 호응을 확인하는 것이 고득점의 비결입니다!"
    if usage == "adjective" or answer.endswith(("한", "적인", "있는", "없는")):
        return f"💡 **일타강사 실전 팁** | {term}은(는) 명사 앞에서 성질이나 상태를 묘사하는 형용사 어휘입니다. 형용사 문제는 꾸며주는 명사와의 어울림이 가장 중요하므로, 명사와 한 덩어리로 묶어서(콜로케이션) 입으로 낭독하며 감을 잡는 것이 제일 좋습니다!"
    return f"💡 **일타강사 실전 팁** | {term}은(는) 파트 5/6의 대표적인 명사 어휘입니다. 명사 문제는 단어의 성질(사람/사물, 가산/불가산)과 빈칸 앞뒤의 동사/전치사 짝꿍을 맞춰 정답을 유추하는 것이 핵심 전략입니다!"



def find_term_for_meaning(meaning: str, entries: list[dict]) -> str:
    for entry in entries:
        if entry.get("answer") == meaning:
            return entry["term"]
    return ""


def find_meaning_for_term(term: str, entries: list[dict]) -> str:
    for entry in entries:
        if entry.get("term") == term:
            return entry["answer"]
    return ""


def build_vocab_explanation(
    term: str,
    answer: str,
    meanings_list: list[str],
    direction: str,
    choices: list[str],
    entries: list[dict],
    usage: str,
    has_context: bool = True
) -> str:
    secondary_meanings = [m for m in meanings_list if m != answer]
    if secondary_meanings:
        sec_str = ", ".join(dict.fromkeys(secondary_meanings))
        header = f"📖 **어휘 의미** | **{answer}** (기타 의미: {sec_str})\n\n"
    else:
        header = f"📖 **어휘 의미** | **{answer}**\n\n"

    
    if direction == "meaning":
        letter = "ABCD"[choices.index(answer)] if answer in choices else "?"
        if has_context:
            exposition = f"어휘 해설 | 문맥 속에서 가장 알맞은 뜻을 고르는 문제입니다. 문장 속에서 **{term}**은 **'{answer}'**(으)로 쓰였습니다. 따라서 정답은 ({letter})입니다."
        else:
            exposition = f"어휘 해설 | 제시된 단어 **{term}**은(는) **'{answer}'**을(를) 뜻합니다. 따라서 정답은 ({letter})입니다."
    elif direction == "term":
        letter = "ABCD"[choices.index(term)] if term in choices else "?"
        exposition = f"어휘 해설 | 한글 뜻 **'{answer}'**에 해당하는 올바른 영단어를 고르는 문제입니다. 정답인 **{term}**은 **'{answer}'**을(를) 뜻합니다. 따라서 정답은 ({letter})입니다."
    else: # word
        letter = "ABCD"[choices.index(term)] if term in choices else "?"
        exposition = f"어휘 해설 | 문맥상 빈칸에 들어갈 가장 알맞은 어휘를 고르는 문제입니다. 문장에 **{term}**('{answer}')을(를) 넣었을 때 의미가 자연스럽습니다. 따라서 정답은 ({letter})입니다."

        
    analysis_lines = []
    for choice in choices:
        if direction == "meaning":
            if choice == answer:
                continue
            dist_term = find_term_for_meaning(choice, entries)
            if dist_term:
                analysis_lines.append(f"- **{choice}** : 영단어 **{dist_term}**의 뜻입니다.")
            else:
                analysis_lines.append(f"- **{choice}**")
        else: # term or word
            if choice == term:
                continue
            dist_meaning = find_meaning_for_term(choice, entries)
            if dist_meaning:
                analysis_lines.append(f"- **{choice}** : '{dist_meaning}'을(를) 뜻합니다.")
            else:
                analysis_lines.append(f"- **{choice}**")
                
    analysis_text = "오답 분석 |\n" + ("\n".join(analysis_lines) if analysis_lines else "선택지의 다른 단어들도 함께 분석하면 단어량이 빠르게 늘어납니다.")
    
    tip = vocab_tip(term, answer, usage)
    toeic_point = f"토익 포인트 | {tip}"
    
    return f"{header}{exposition}\n\n{analysis_text}\n\n{toeic_point}"


def vocab_grammar_note(term: str, answer: str, usage: str, choices: list[str], entries: list[dict]) -> str:
    return build_vocab_explanation(term, answer, [answer], "meaning", choices, entries, usage, has_context=False)



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


def contains_korean(s: str) -> bool:
    return any(0xAC00 <= ord(c) <= 0xD7A3 or 0x1100 <= ord(c) <= 0x11FF for c in s)


def is_overlapping(val1: str, val2: str) -> bool:
    # 1. Normalize spacing and lowercase
    s1 = "".join(val1.lower().split())
    s2 = "".join(val2.lower().split())
    
    # 2. Check substring relation
    if s1 in s2 or s2 in s1:
        return True
        
    # 3. Split by common Korean separators and check intersection
    parts1 = set(p.strip().lower() for p in re.split(r'[,;/~()]', val1) if p.strip())
    parts2 = set(p.strip().lower() for p in re.split(r'[,;/~()]', val2) if p.strip())
    
    if parts1.intersection(parts2):
        return True
        
    return False


def stable_choices(answer: str, answers: list[str], seed: str) -> list[str]:
    pool = [candidate for candidate in dict.fromkeys(answers) if candidate != answer]
    start = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16) if pool else 0
    distractors: list[str] = []
    index = start
    attempts = 0
    max_attempts = len(pool) * 2
    
    while pool and len(distractors) < 3 and attempts < max_attempts:
        candidate = pool[index % len(pool)]
        attempts += 1
        index += 17
        if candidate in distractors:
            continue
        if contains_korean(answer) or contains_korean(candidate):
            if is_overlapping(candidate, answer) or any(is_overlapping(candidate, d) for d in distractors):
                continue
        distractors.append(candidate)
        
    if len(distractors) < 3:
        for candidate in pool:
            if len(distractors) >= 3:
                break
            if candidate not in distractors and candidate != answer:
                distractors.append(candidate)
                
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


def infer_usage_from_meaning(term: str, meaning: str) -> str:
    lower = term.strip().lower()
    meaning = meaning.strip()
    if " " in lower:
        if lower.startswith(("in ", "at ", "on ", "by ", "for ", "with ", "without ", "due to", "owing to")):
            return "adverbial-phrase"
        if lower.startswith(("be ", "become ", "remain ")):
            return "verb-phrase"
        if "하다" in meaning:
            return "verb-phrase"
        return "noun-phrase"
    if "하다" in meaning or meaning.endswith("되다") or meaning.endswith("하다"):
        return "verb"
    if meaning.endswith(("한", "있는", "없는", "적인", "된", "할")):
        return "adjective"
    if lower.endswith("ly") or meaning.endswith(("게", "히", "으로")):
        return "adverb"
    return "noun"


def korean_particle(value: str) -> str:
    if not value:
        return "을"
    code = ord(value[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return "을" if (code - 0xAC00) % 28 else "를"
    return "을"


SMART_VOCAB_REGISTRY = {
    "executive": {
        "sentence": "The chief executive officer decided to delay the launch of the new software.",
        "sentenceKo": "최고 경영진(임원)은 새로운 소프트웨어의 출시를 연기하기로 결정했다.",
        "grammarNote": "executive는 '경영진, 임원'이라는 뜻의 명사이며, '경영의, 임원진의'라는 형용사로도 널리 쓰입니다. 비즈니스 직책(executive officer) 등에 단골로 출제되는 어휘입니다."
    },
    "accommodation": {
        "sentence": "The hotel provides luxury accommodations and excellent service for business travelers.",
        "sentenceKo": "그 호텔은 비즈니스 여행객들에게 호화로운 숙박 시설과 훌륭한 서비스를 제공한다.",
        "grammarNote": "accommodation은 '숙박 시설, 편의 시설'이라는 뜻의 명사로, 토익에서는 대개 복수형인 accommodations 형태로 빈출되므로 함께 외우는 것이 요령입니다."
    },
    "temporary": {
        "sentence": "The HR manager hired a temporary employee to handle the administrative tasks during summer.",
        "sentenceKo": "인사 담당자는 여름 동안 행정 업무를 처리하기 위해 임시 직원을 고용했다.",
        "grammarNote": "temporary는 '임시의, 일시적인'이라는 뜻의 형용사로, 반대어인 permanent(정구적인, 영구의)와 대비하여 자격이나 상태를 묻는 단어로 빈출됩니다."
    },
    "contribute": {
        "sentence": "All staff members are encouraged to contribute their ideas to the marketing campaign.",
        "sentenceKo": "모든 직원들은 마케팅 캠페인에 그들의 아이디어를 기여하도록 권장된다.",
        "grammarNote": "contribute는 '기여하다, 공헌하다'라는 뜻의 동사로, 목적어를 직접 취해 'A를 기여하다'로 쓰이거나, 자동사로서 contribute to 명사 (~에 기여하다) 형태로 매우 빈출됩니다."
    },
    "accumulate": {
        "sentence": "Customers can accumulate reward points every time they make a purchase online.",
        "sentenceKo": "고객들은 온라인으로 구매를 할 때마다 적립 포인트를 축적할(모을) 수 있다.",
        "grammarNote": "accumulate는 '축적하다, 모으다'라는 뜻의 타동사로, 주로 포인트(points), 경험(experience), 자금(wealth) 등을 목적으로 취해 비즈니스 혜택 설명에서 출제됩니다."
    },
    "applicant": {
        "sentence": "Each applicant must submit their references along with the updated resume.",
        "sentenceKo": "각 지원자는 업데이트된 이력서와 함께 추천서를 제출해야 한다.",
        "grammarNote": "applicant는 '지원자, 신청자'라는 뜻의 명사로, 동사인 apply(지원하다), 명사인 application(지원서, 신청서)과 형태를 구분하는 품사 자격 문제로 자주 출제됩니다."
    },
    "implement": {
        "sentence": "The board decided to implement new security measures at the headquarters.",
        "sentenceKo": "이사회는 본사에 새로운 보안 조치를 시행하기로 결정했다.",
        "grammarNote": "implement는 '(정책, 규칙, 계획 등을) 시행하다, 이행하다'라는 뜻의 대표 동사로, carry out와 동의어로 쓰이며 뒤에 정책(policy)이나 조치(measures)를 목적어로 자주 취합니다."
    },
    "postpone": {
        "sentence": "The management team had to postpone the planning meeting until next Monday.",
        "sentenceKo": "경영진은 기획 회의를 다음 주 월요일까지 연기해야 했다.",
        "grammarNote": "postpone은 '연기하다, 미루다'라는 뜻의 동사로, delay, put off 등과 유사어입니다. 전치사 until, to 등과 함께 시점을 연기하는 문맥에서 주로 출제됩니다."
    },
    "renew": {
        "sentence": "Clients who wish to renew their subscription should contact customer service.",
        "sentenceKo": "구독을 갱신하고자 하는 고객은 고객 서비스 부서에 연락해야 한다.",
        "grammarNote": "renew는 '갱신하다, 재개하다'라는 뜻의 동사로, 주로 계약(contract), 구독(subscription), 회원 자격(membership) 등을 갱신하는 비즈니스 거래 맥락에서 출제됩니다."
    },
    "reimburse": {
        "sentence": "The company will reimburse employees for travel expenses incurred during the business trip.",
        "sentenceKo": "회사는 출장 중 발생한 여비를 직원들에게 변제해 줄(비용을 돌려줄) 것이다.",
        "grammarNote": "reimburse는 '변제하다, 상환하다'라는 뜻의 중요 동사로, 주로 'reimburse A for B' (A에게 B 비용을 돌려주다) 구조로 전치사 for와 짝을 이루어 단골 출제됩니다."
    },
    "compliance": {
        "sentence": "The factory operates in strict compliance with safety regulations.",
        "sentenceKo": "그 공장은 안전 규정을 엄격히 준수하여 운영된다.",
        "grammarNote": "compliance는 '(규정, 법의) 준수, 따름'이라는 뜻의 명사로, 동사인 comply(comply with, 준수하다)와 짝을 이루며 'in compliance with' (~을 준수하여)라는 통째 숙어 표현으로 매우 빈출됩니다."
    },
    "allocate": {
        "sentence": "The city council agreed to allocate funds for the renovation of the public park.",
        "sentenceKo": "시 의회는 공공 공원의 개보수를 위해 자금을 할당하기로 합의했다.",
        "grammarNote": "allocate는 '(자금, 시간 등을) 할당하다, 배분하다'라는 동사로, budget(예산을 책정하다)이나 assign(배정하다)과 유사한 맥락에서 예산 분배 시 출제됩니다."
    },
    "alternative": {
        "sentence": "We must find alternative solutions if the supplier fails to deliver on time.",
        "sentenceKo": "공급업체가 제때 납품하지 못할 경우 우리는 대안적인 해결책을 찾아야 한다.",
        "grammarNote": "alternative는 명사로 '대안'이라는 뜻 외에도 형용사로서 '대안적인, 다른'이라는 뜻으로 쓰입니다. 명사를 꾸미는 형용사 자리에 자주 출제됩니다."
    },
    "approximately": {
        "sentence": "The construction project will take approximately three months to complete.",
        "sentenceKo": "건설 프로젝트를 완료하는 데 대략 3개월이 소요될 것이다.",
        "grammarNote": "approximately는 '대략, 거의'라는 뜻의 부사로, 숫자나 기간 표현(three months 등)을 앞에서 수식하며 정도를 조절하는 부사 어휘로 토익에 빈출됩니다."
    },
    "negotiate": {
        "sentence": "The purchasing department was able to negotiate a better price with the vendor.",
        "sentenceKo": "구매 부서는 판매업체와 더 나은 가격을 협상할 수 있었다.",
        "grammarNote": "negotiate는 '협상하다, 절충하다'라는 뜻의 동사로, 주로 negotiate with 대상 (누구와 협상하다), negotiate a contract (계약을 타결하다) 등의 콜로케이션으로 쓰います."
    },
    "authorize": {
        "sentence": "Only the department manager is allowed to authorize overtime work.",
        "sentenceKo": "부서장만이 시간 외 근무를 승인할(권한을 부여할) 수 있다.",
        "grammarNote": "authorize는 '승인하다, 권한을 부여하다'라는 뜻의 동사로, 형용사인 authorized (공인된, 승인된) 및 명사인 authority (권한, 당국)와 구분하는 법을 묻습니다."
    },
    "confidential": {
        "sentence": "Employees are strictly prohibited from sharing confidential client documents.",
        "sentenceKo": "직원들은 기밀 고객 문서를 공유하는 것이 엄격히 금지된다.",
        "grammarNote": "confidential은 '기밀의, 비밀의'라는 형용사로, 주로 서류(documents), 정보(information), 업무(records) 등의 명사를 꾸며 보안 규정 관련 지문에서 자주 출제됩니다."
    },
    "collaboration": {
        "sentence": "The new product was developed in close collaboration with our overseas partners.",
        "sentenceKo": "신제품은 우리의 해외 파트너들과의 긴밀한 협력을 통해 개발되었다.",
        "grammarNote": "collaboration은 '협력, 공동 작업'이라는 명사로, 'in collaboration with' (~와 협력하여)라는 형태로 자주 쓰이며, 동사 collaborate(협력하다)와 함께 빈출됩니다."
    },
    "delegation": {
        "sentence": "A delegation of industry experts will visit the manufacturing facility tomorrow.",
        "sentenceKo": "업계 전문가 대표단이 내일 제조 시설을 방문할 예정이다.",
        "grammarNote": "delegation은 '대표단'이라는 명사 외에도 '위임, 권한 이양'이라는 추상 명사로도 쓰입니다. 주로 사람들의 집단을 뜻하는 주어로 출제됩니다."
    },
    "evaluate": {
        "sentence": "The supervisor will evaluate the performance of each intern next week.",
        "sentenceKo": "감독관은 다음 주에 각 인턴의 업무 성과를 평가할 것이다.",
        "grammarNote": "evaluate는 '평가하다, 감정하다'라는 동사로, 주로 성과(performance), 가치(value), 계획(proposal)을 목적으로 가집니다. 명사형은 evaluation(평가)입니다."
    },
    "innovative": {
        "sentence": "The startup gained popularity for its innovative design of office furniture.",
        "sentenceKo": "그 스타트업은 사무용 가구의 혁신적인 디자인으로 인기를 얻었다.",
        "grammarNote": "innovative는 '혁신적인, 획기적인'이라는 뜻의 형용사로, 명사인 innovation(혁신)이나 동사 innovate(혁신하다)와 어미를 구분하는 형태로 형용사 자리에 자주 옵니다."
    },
    "mandatory": {
        "sentence": "Attendance at the annual safety training is mandatory for all laboratory staff.",
        "sentenceKo": "연례 안전 교육 참석은 모든 실험실 직원들에게 의무적이다(필수이다).",
        "grammarNote": "mandatory는 '의무적인, 필수의'라는 뜻의 형용사로, compulsory나 required와 유사하며 be동사 뒤 주격 보어 자리나 명사를 수식하는 형용사 자리에 자주 빈출됩니다."
    },
    "objective": {
        "sentence": "The primary objective of the advertising campaign is to increase brand awareness.",
        "sentenceKo": "광고 캠페인의 주요 목적은 브랜드 인지도를 높이는 것이다.",
        "grammarNote": "objective는 명사로 '목적, 목표' (goal, target)라는 뜻을 가지며, 형용사로서는 '객관적인' (반대어: subjective)이라는 뜻을 가집니다. 문맥상 구분이 중요합니다."
    },
    "qualification": {
        "sentence": "Candidates must meet all the qualifications listed in the job description.",
        "sentenceKo": "지원자들은 직무 설명서에 기재된 모든 자격 요건을 충족해야 한다.",
        "grammarNote": "qualification은 '자격 요건, 면허'를 뜻하는 명사로, 동사 meet/satisfy (~을 충족하다)와 어울려 'meet the qualifications' (자격을 충족하다) 패턴으로 자주 나옵니다."
    },
    "revenue": {
        "sentence": "The company reported a significant increase in annual revenue this fiscal year.",
        "sentenceKo": "회사는 이번 회계연도에 연간 총 수입(매출)이 크게 증가했다고 보고했다.",
        "grammarNote": "revenue는 '매출, 수입, 세입'을 뜻하는 명사로, profit(이익)이나 income(소득)과 맥락을 같이 하여 재무 상태나 실적 발표 지문에서 반드시 출제되는 핵심 명사입니다."
    },
    "strategic": {
        "sentence": "The board decided to make a strategic investment in renewable energy resources.",
        "sentenceKo": "이사회는 재생 에너지 자원에 전략적인 투자를 단행하기로 결정했다.",
        "grammarNote": "strategic은 '전략적인, 중요한'이라는 뜻의 형용사로, 명사인 strategy(전략)에서 파생되었습니다. 투자(investment), 제휴(partnership) 등의 명사를 자주 꾸며줍니다."
    },
    "subsequent": {
        "sentence": "The first meeting was brief, but subsequent discussions were much more detailed.",
        "sentenceKo": "첫 회의는 짧았지만, 그 이후의(차후의) 논의들은 훨씬 더 상세했다.",
        "grammarNote": "subsequent는 '그 다음의, 차후의'라는 뜻의 형용사로, 주로 시간이나 사건의 선후 관계를 묘사할 때 명사(years, events, discussions) 앞에 쓰입니다."
    },
    "termination": {
        "sentence": "Early termination of the lease contract requires a written notice 30 days in advance.",
        "sentenceKo": "임대차 계약의 조기 해지(종료)는 30일 전에 서면 통지가 필요하다.",
        "grammarNote": "termination은 '종료, 해지, 완결'이라는 뜻의 명사로, 주로 계약(contract, lease)이나 고용 관계의 종료를 나타내는 법률 및 비즈니스 조항에서 자주 출제됩니다."
    },
    "unanimous": {
        "sentence": "The board members reached a unanimous agreement to appoint the new director.",
        "sentenceKo": "이사회 멤버들은 신임 이사를 임명하는 것에 만장일치의 합의에 도달했다.",
        "grammarNote": "unanimous는 '만장일치의, 의견이 같은'이라는 형용사로, 주로 합의(agreement), 투표(vote), 지원(support) 등의 명사와 어울려 쓰입니다."
    },
    "vendor": {
        "sentence": "We need to compare price quotes from different vendors before purchasing the equipment.",
        "sentenceKo": "장비를 구매하기 전에 여러 판매업체의 견적서를 비교해야 한다.",
        "grammarNote": "vendor는 '판매 회사, 상인'이라는 명사로, supplier(공급업체)나 merchant(상인)와 결합하여 물품 계약 지문에서 단골로 쓰이는 단어입니다."
    },
    "warranty": {
        "sentence": "The manufacturer offers a one-year warranty on all electronic appliances.",
        "sentenceKo": "제조업체는 모든 가전제품에 대해 1년의 품질 보증서를 제공한다.",
        "grammarNote": "warranty는 '보증, 품질 보증서'라는 뜻의 명사로, 주로 'under warranty' (보증 기간 내에 있는) 또는 'extended warranty' (연장 보증) 등의 콜로케이션으로 빈출됩니다."
    },
    "supervision": {
        "sentence": "All construction tasks must be completed under the direct supervision of the chief engineer.",
        "sentenceKo": "모든 건설 작업은 수석 엔지니어의 직접적인 감독 하에 완료되어야 한다.",
        "grammarNote": "supervision은 '감독, 관리'라는 뜻의 명사로, 주로 'under the supervision of' (~의 감독 하에)라는 숙어 패턴으로 단골 출제되는 비즈니스 어휘입니다."
    },
    "feature": {
        "sentence": "The new smartphone model boasts a unique security feature that utilizes facial recognition.",
        "sentenceKo": "새 스마트폰 모델은 얼굴 인식을 활용하는 독특한 보안 기능을 자랑한다.",
        "grammarNote": "feature는 명사로 '특징, 특색' 외에도 동사로 '특별히 포함하다, 특집으로 다루다'라는 뜻이 있어 품사 구분이 아주 중요합니다."
    },
    "inventory": {
        "sentence": "The store manager conducted a physical count to update the inventory records.",
        "sentenceKo": "매장 매니저는 재고 기록을 업데이트하기 위해 실제 실사 조사를 수행했다.",
        "grammarNote": "inventory는 '재고, 재고 목록'이라는 뜻의 대표적인 비즈니스 명사입니다. 'take inventory'는 '재고 조사를 하다'라는 중요 숙어로 출제됩니다."
    },
    "acquire": {
        "sentence": "The conglomerate aims to acquire the small technology startup to expand its market share.",
        "sentenceKo": "그 대기업은 시장 점유율을 확장하기 위해 소규모 기술 스타트업을 인수하는 것을 목표로 한다.",
        "grammarNote": "acquire는 기업 간 인수합병(M&A) 지문에서 '인수하다'라는 타동사로 매우 빈출됩니다. 명사형은 acquisition(인수, 획득)입니다."
    },
    "designated": {
        "sentence": "Please park your vehicle only in the designated areas to avoid being fined.",
        "sentenceKo": "벌금을 물지 않으려면 지정된 구역에만 차량을 주차해 주십시오.",
        "grammarNote": "designated는 동사 designate(지정하다)의 과거분사형 형용사로, 구역(areas), 주차 공간(parking spaces) 등의 명사 수식 문제로 자주 출제됩니다."
    },
    "precaution": {
        "sentence": "As a safety precaution, all construction workers must wear protective headgear.",
        "sentenceKo": "안전 예방 조치로서 모든 건설 노동자들은 보호용 헬멧을 착용해야 한다.",
        "grammarNote": "precaution은 주로 'take precautions' (예방 조치를 취하다) 또는 'safety precautions' (안전 예방 조치)라는 복수 콜로케이션으로 빈출됩니다."
    },
    "unprecedented": {
        "sentence": "The company experienced unprecedented growth in online sales during the second quarter.",
        "sentenceKo": "그 회사는 2분기 동안 온라인 매출에서 전례 없는 성장을 경험했다.",
        "grammarNote": "unprecedented는 '전례 없는, 사상 초유의'라는 뜻의 고급 형용사로 growth, success, demand 등과 결합하여 출제됩니다."
    },
    "anticipate": {
        "sentence": "Analysts anticipate that interest rates will remain stable for the next fiscal year.",
        "sentenceKo": "분석가들은 다음 회계연도 동안 금리가 안정세를 유지할 것으로 예상한다.",
        "grammarNote": "anticipate는 타동사로서 주로 that절을 목적어로 취하며, expect나 predict와 유사한 출제 맥락을 가집니다."
    },
    "reluctant": {
        "sentence": "Board members were reluctant to invest in the risky venture without further analysis.",
        "sentenceKo": "이사회 멤버들은 추가 분석 없이 위험한 벤처에 투자하기를 꺼렸다.",
        "grammarNote": "reluctant는 'be reluctant to + 동사원형' (~하기를 꺼리다) 패턴으로 출제되는 단골 형용사입니다. 유의어로는 hesitant가 있습니다."
    },
    "collaborate": {
        "sentence": "Researchers from both institutions will collaborate on the new medical study.",
        "sentenceKo": "양 기관의 연구원들이 새로운 의학 연구에 협력할 것이다.",
        "grammarNote": "collaborate는 자동사이므로 'collaborate on 주제' (~에 대해 협력하다), 'collaborate with 대상' (~와 협력하다) 전치사 결합 문제가 출제됩니다."
    },
    "provisional": {
        "sentence": "The provisional schedule for the international conference is subject to change.",
        "sentenceKo": "국제 회의의 잠정적인 일정은 변경될 수 있다.",
        "grammarNote": "provisional은 temporary와 유의어로, provisional agreement(잠정 합의), provisional schedule(잠정 일정) 등으로 출제됩니다."
    },
    "substantially": {
        "sentence": "Operating costs decreased substantially after the company upgraded its equipment.",
        "sentenceKo": "회사가 장비를 업그레이드한 후 운영 비용이 상당히 감소했다.",
        "grammarNote": "substantially는 증감 동사(increase, decrease, fall, rise)를 수식하는 중요 부사로, significantly, dramatically 등과 유의어입니다."
    },
    "meticulous": {
        "sentence": "The accounting firm is known for its meticulous attention to financial details.",
        "sentenceKo": "그 회계법인은 재무 세부사항에 대한 꼼꼼한 주의로 잘 알려져 있다.",
        "grammarNote": "meticulous는 'meticulous attention to' (~에 대한 세심한 주의) 형태로 자주 출제되며, 매우 꼼꼼한 성격이나 철저한 검수를 나타낼 때 쓰입니다."
    },
    "commence": {
        "sentence": "The construction of the new office building is scheduled to commence in July.",
        "sentenceKo": "신축 사옥 건설은 7월에 시작될 예정이다.",
        "grammarNote": "commence는 begin 이나 start 의 비즈니스 공식 표현으로, 자동사와 타동사 모두 가능합니다. 명사형은 commencement(시작, 졸업식)입니다."
    },
    "adversely": {
        "sentence": "The profits of the airline were adversely affected by the sudden rise in fuel prices.",
        "sentenceKo": "그 항공사의 수익은 연료 가격의 갑작스러운 상승으로 인해 부정적인 영향을 받았다.",
        "grammarNote": "adversely는 주로 수동태와 결합하여 'be adversely affected by' (~에 의해 부정적 영향을 받다)의 덩어리 수식 문제로 빈출됩니다."
    },
    "stringent": {
        "sentence": "The local government enforced stringent safety standards for all building projects.",
        "sentenceKo": "지방 정부는 모든 빌딩 프로젝트에 대해 엄격한 안전 기준을 집행했다.",
        "grammarNote": "stringent는 strict나 rigorous와 유의어로, 규정(rules, regulations), 검사(inspection), 기준(standards) 등을 엄격하게 집행할 때 쓰입니다."
    },
    "expedite": {
        "sentence": "Customers can pay an extra fee to expedite the shipping of their orders.",
        "sentenceKo": "고객들은 주문 상품의 배송을 신속히 처리하기 위해 추가 요금을 지불할 수 있다.",
        "grammarNote": "expedite는 비즈니스 거래나 주문 처리 지문에서 'process quickly'의 뜻으로 빈출되는 고급 타동사입니다."
    },
    "lucrative": {
        "sentence": "The consulting firm secured a lucrative contract with a multinational corporation.",
        "sentenceKo": "그 컨설팅 회사는 다국적 기업과 수익성이 좋은 계약을 따냈다.",
        "grammarNote": "lucrative는 '돈벌이가 잘 되는'이라는 뜻으로, contract(계약), business(사업), market(시장) 등과 단골 매치됩니다."
    },
    "jeopardize": {
        "sentence": "A budget deficit could jeopardize the development of the new product line.",
        "sentenceKo": "예산 적자는 신제품 라인의 개발을 위태롭게 할 수 있다.",
        "grammarNote": "jeopardize는 위험에 빠뜨리다(endanger)의 비즈니스적 표현으로 출제 빈도가 높습니다."
    },
    "confidentiality": {
        "sentence": "All employees must sign a confidentiality agreement before accessing sensitive data.",
        "sentenceKo": "모든 직원들은 민감한 데이터에 접근하기 전에 비밀 유지 합의서에 서명해야 한다.",
        "grammarNote": "confidentiality는 'confidentiality agreement' (비밀유지 계약)라는 복합명사 자격 혹은 명사형 구분 문제로 출제됩니다."
    },
    "redundant": {
        "sentence": "The merger made several administrative positions redundant.",
        "sentenceKo": "그 합병으로 인해 몇몇 행정 직책이 중복되어 불필요해졌다.",
        "grammarNote": "redundant는 비즈니스 구조 조정 지문에서 '불필요한, 남는' 혹은 '해고된'의 의미로 출제됩니다."
    },
    "reception": {
        "sentence": "The hotel reception is located on the ground floor next to the elevator.",
        "sentenceKo": "호텔 접수처는 1층 엘리베이터 옆에 위치해 있다.",
        "grammarNote": "reception은 '접수처, 프런트'라는 장소적 의미 외에도 '환영회, 리셉션'이라는 사교 행사 의미로도 토익에 빈출됩니다."
    },
    "inspect": {
        "sentence": "Safety inspectors will inspect the manufacturing plant to ensure full compliance.",
        "sentenceKo": "안전 검사관들이 완벽한 준수를 보장하기 위해 제조 공장을 검사할 것이다.",
        "grammarNote": "inspect는 '검사하다, 점검하다'라는 동사로, 명사형은 inspection(검사, 점검), 사람 명사형은 inspector(검사관)입니다."
    },
    "exclusively": {
        "sentence": "The VIP lounge is exclusively reserved for first-class passengers.",
        "sentenceKo": "VIP 라운지는 오직 일등석 승객들만을 위해 독점적으로 예약되어 있다.",
        "grammarNote": "exclusively는 '독점적으로, 오직(solely)'의 뜻으로 부사 어휘 문제로 자주 정답이 됩니다."
    },
    "comprehensive": {
        "sentence": "The training manual offers a comprehensive overview of our software systems.",
        "sentenceKo": "교육 매뉴얼은 당사 소프트웨어 시스템에 대한 종합적인 개요를 제공한다.",
        "grammarNote": "comprehensive는 '포괄적인, 종합적인'이라는 뜻의 단골 형용사입니다. 명사 comprehension(이해력)과 형태를 구분해야 합니다."
    },
    "outstanding": {
        "sentence": "Employees with outstanding performance will be considered for a promotion.",
        "sentenceKo": "우수한 성과를 낸 직원들이 승진 대상자로 고려될 것이다.",
        "grammarNote": "outstanding is '뛰어난, 우수한'이라는 뜻 외에 '미지불된, 미결제된(unpaid)'의 뜻으로 회계 및 대금 청구 지문에 빈출됩니다."
    },
    "preliminary": {
        "sentence": "The committee released the preliminary findings of the market research.",
        "sentenceKo": "위원회는 시장 조사의 예비 조사 결과를 발표했다.",
        "grammarNote": "preliminary는 '예비의, 준비 단계의'라는 형용사로, preliminary results/findings(예비 결과) 등의 콜로케이션으로 쓰입니다."
    },
    "reputable": {
        "sentence": "We recommend buying office equipment only from reputable suppliers.",
        "sentenceKo": "평판이 좋은 공급업체로부터만 사무 장비를 구매할 것을 권장합니다.",
        "grammarNote": "reputable은 명사 reputation(평판)에서 유래한 형용사로, '평판이 좋은, 유명한'의 뜻을 지닙니다."
    },
    "deteriorate": {
        "sentence": "The weather conditions are expected to deteriorate further over the weekend.",
        "sentenceKo": "기상 조건이 주말 동안 더 악화될 것으로 예상된다.",
        "grammarNote": "deteriorate는 '악화되다, 나빠지다'라는 뜻의 자동사로, 기후나 건강, 시장 상황이 나빠질 때 쓰입니다."
    },
    "unanimously": {
        "sentence": "The city council unanimously voted to approve the new public transit budget.",
        "sentenceKo": "시 의회는 새로운 대중교통 예산을 만장일치로 승인하기로 투표했다.",
        "grammarNote": "unanimously는 형용사 unanimous(만장일치의)에서 파생된 부사로, 의사결정 투표 지문에서 동사(vote, approve 등)를 수식합니다."
    },
    "delinquent": {
        "sentence": "The bank sends reminder notices to clients with delinquent accounts.",
        "sentenceKo": "은행은 연체 계좌가 있는 고객들에게 알림 통지서를 보낸다.",
        "grammarNote": "delinquent는 세금이나 요금, 대출 상환 등이 '연체된, 체납된(overdue)'의 뜻으로 금융 분야에 빈출됩니다."
    }
}

VOCAB_TEMPLATES = {
    "verb": [
        {
            "sentence": "The committee decided to {term} the new policy starting next business quarter.",
            "sentenceKo": "위원회는 다음 비즈니스 분기부터 새로운 정책을 {meaning}하기로 결정했다."
        },
        {
            "sentence": "Please {term} the document carefully before submitting it to the executive board.",
            "sentenceKo": "이사회에 제출하기 전에 문서를 주의 깊게 {meaning}하십시오."
        },
        {
            "sentence": "The corporation hopes to {term} its retail operations in the European market.",
            "sentenceKo": "기업은 유럽 시장에서 소매 운영을 {meaning}하기를 희망한다."
        }
    ],
    "adjective": [
        {
            "sentence": "All staff members must provide {term} updates on their project status.",
            "sentenceKo": "모든 직원들은 그들의 프로젝트 상태에 대해 {meaning} 업데이트를 제공해야 한다."
        },
        {
            "sentence": "The manager requested a {term} analysis of the quarterly marketing results.",
            "sentenceKo": "관리자는 분기별 마케팅 결과에 대한 {meaning} 분석을 요청했다."
        },
        {
            "sentence": "Our developers are working hard to find a {term} solution to the software error.",
            "sentenceKo": "우리 개발자들은 소프트웨어 오류에 대한 {meaning} 해결책을 찾기 위해 열심히 노력하고 있다."
        }
    ],
    "adverb": [
        {
            "sentence": "The technical team resolved the server connection issues {term} after the meeting.",
            "sentenceKo": "기술 팀은 회의 직후 서버 연결 문제를 {meaning} 해결했다."
        },
        {
            "sentence": "The new guidelines on business trips were {term} approved by the financial director.",
            "sentenceKo": "출장에 관한 새로운 가이드라인이 재무 이사에 의해 {meaning} 승인되었다."
        },
        {
            "sentence": "Please review the safety guidelines {term} before operating the new machinery.",
            "sentenceKo": "새로운 기계를 가동하기 전에 안전 가이드라인을 {meaning} 검토하시기 바랍니다."
        }
    ],
    # 일반 명사 (사물 및 추상 개념)
    "noun-thing": [
        {
            "sentence": "Please send the completed {term} to the administration office as soon as possible.",
            "sentenceKo": "완성된 {meaning}{particle} 가능한 한 빨리 행정실로 보내주시기 바랍니다."
        },
        {
            "sentence": "The board members had a brief discussion about the proposed {term} last night.",
            "sentenceKo": "이사회 멤버들은 어젯밤 제안된 {meaning}에 대해 짧은 논의를 거쳤다."
        },
        {
            "sentence": "The management implements a new system to optimize the overall {term}.",
            "sentenceKo": "경영진은 전반적인 {meaning}{particle} 최적화하기 위해 새로운 시스템을 도입한다."
        }
    ],
    # 사람 명사 (행위자, 직책)
    "noun-person": [
        {
            "sentence": "The agency hired a highly qualified {term} to manage the public relations campaign.",
            "sentenceKo": "대행사는 홍보 캠페인을 관리할 자격 있는 {meaning}{particle} 고용했다."
        },
        {
            "sentence": "Each {term} is requested to submit their credentials to the manager by Friday.",
            "sentenceKo": "각 {meaning}은(는) 금요일까지 관리자에게 자격 증명서를 제출할 것이 요구된다."
        },
        {
            "sentence": "A designated {term} will guide the visitors through the research facility.",
            "sentenceKo": "지정된 {meaning}{particle} 연구 시설로 방문객들을 안내할 것이다."
        }
    ],
    "noun": [
        {
            "sentence": "Please send the completed {term} to the administration office as soon as possible.",
            "sentenceKo": "완성된 {meaning}{particle} 가능한 한 빨리 행정실로 보내주시기 바랍니다."
        }
    ],
    "adverbial-phrase": [
        {
            "sentence": "All personnel are required to work {term} to complete the product launch on schedule.",
            "sentenceKo": "모든 직원들은 신제품 출시를 예정대로 완료하기 위해 {meaning} 일해야 한다."
        },
        {
            "sentence": "The time table for the training seminar has been revised {term} due to scheduling conflicts.",
            "sentenceKo": "일정 충돌로 인해 교육 세미나 시간표가 {meaning} 변경되었다."
        },
        {
            "sentence": "Please note that database backups must be completed {term} to prevent any data loss.",
            "sentenceKo": "데이터 손실을 방지하기 위해 데이터베이스 백업은 {meaning} 수행되어야 함에 유의하십시오."
        }
    ],
    "verb-phrase": [
        {
            "sentence": "The public relations department plans to {term} before the end of this month.",
            "sentenceKo": "홍보 부서는 이번 달 말 전에 {meaning}할 계획이다."
        },
        {
            "sentence": "Staff members are expected to {term} to maintain a highly productive work environment.",
            "sentenceKo": "직원들은 매우 생산적인 근무 환경을 유지하기 위해 {meaning}할 것으로 기대된다."
        },
        {
            "sentence": "The president hopes that our department will {term} for the development of new programs.",
            "sentenceKo": "사장은 우리 부서가 새로운 프로그램 개발을 위해 {meaning}하기를 바란다."
        }
    ]
}


def numbered_vocab_note(entry: dict, direction: str, choices: list[str], entries: list[dict], has_context: bool) -> str:
    term = entry["term"]
    answer = entry["answer"]
    meanings_list = entry.get("meanings") or [answer]
    usage = infer_usage_from_meaning(term, answer)
    return build_vocab_explanation(term, answer, meanings_list, direction, choices, entries, usage, has_context)



def stable_choices_by_usage(answer: str, usage: str, entries: list[dict], pool_key: str, seed: str) -> list[str]:
    # 1단계: 동일 품사(usage)를 가졌으면서 다른 단어인 것들을 오답 풀로 채택
    same_usage_pool = []
    for entry in entries:
        entry_term = entry["term"]
        entry_answer = entry["answer"]
        entry_usage = infer_usage_from_meaning(entry_term, entry_answer)
        if entry_usage == usage:
            val = entry["answer"] if pool_key == "answer" else entry["term"]
            if val != answer and val not in same_usage_pool:
                same_usage_pool.append(val)
                
    # 품사 일치 풀만 사용
    final_pool = same_usage_pool
    # 만약 동일 품사 풀이 극도로 부족하여 오답 3개를 채울 수 없는 특수 상황일 때만 전체 풀로 폴백
    if len(final_pool) < 3:
        all_pool = []
        for entry in entries:
            val = entry["answer"] if pool_key == "answer" else entry["term"]
            if val != answer and val not in all_pool:
                all_pool.append(val)
        for val in all_pool:
            if val not in final_pool:
                final_pool.append(val)
            
    # 4단계: 해시 시드를 이용해 오답 3개 무작위 선출 (중복/유사 의미 방지 적용)
    start = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16) if final_pool else 0
    distractors = []
    index = start
    attempts = 0
    max_attempts = len(final_pool) * 2
    while final_pool and len(distractors) < 3 and attempts < max_attempts:
        candidate = final_pool[index % len(final_pool)]
        attempts += 1
        index += 29 # 해시 기반 분산 점프
        if candidate in distractors:
            continue
        if contains_korean(answer) or contains_korean(candidate):
            if is_overlapping(candidate, answer) or any(is_overlapping(candidate, d) for d in distractors):
                continue
        distractors.append(candidate)
        
    if len(distractors) < 3:
        for candidate in final_pool:
            if len(distractors) >= 3:
                break
            if candidate not in distractors and candidate != answer:
                distractors.append(candidate)
        
    choices = [answer] + distractors
    choices.sort()
    return choices



def build_numbered_vocab_items() -> list[dict]:
    entries = load_numbered_vocab_entries()
    items: list[dict] = []

    for entry in entries:
        number = entry["number"]
        term = entry["term"]
        answer = entry["answer"]
        tags = numbered_vocab_tags(number)
        # 품사 판정
        usage = infer_usage_from_meaning(term, answer)

        base = {
            "term": term,
            "termKey": normalize_space(term).lower(),
            "source": entry["source"],
            "sourcePath": entry["sourcePath"],
            "quality": "approved",
            "contextType": "vocabulary",
            "grammarFocus": usage,
            "tags": tags,
            "vocabNumber": number,
        }

        # 기본값 (사전 매핑되지 않았을 때의 템플릿 사용)
        has_smart = term.lower() in SMART_VOCAB_REGISTRY
        if has_smart:
            smart = SMART_VOCAB_REGISTRY[term.lower()]
            meaning_sentence = smart["sentence"]
            meaning_sentence_ko = smart["sentenceKo"]
            custom_note = smart["grammarNote"]
        else:
            meaning_sentence = term
            meaning_sentence_ko = f"{term}: {answer}"
            custom_note = (
                "💡 **일타강사 실전 압축 팁** | 동사는 문장의 뼈대입니다. 동사 어휘 문제를 풀 때는 먼저 빈칸 뒤에 목적어(명사구)가 있는지를 보아 타동사인지 자동사인지 판별하고, 주어와의 수 일치 ➔ 수동/능동태 ➔ 단서 시제의 3단계 법칙을 적용하세요!" if usage in {"verb", "verb-phrase"} else
                "💡 **일타강사 실전 압축 팁** | 형용사는 명사 바로 앞에서 수식하거나, be동사/keep/remain 등 2형식 동사 뒤 주격 보어 자리에서 출제됩니다. 분사형 형용사(e.g., -ing, -ed)와의 구분 및 짝이 되는 명사의 관계를 잡는 것이 득점 비결입니다!" if usage == "adjective" else
                "💡 **일타강사 실전 압축 팁** | 부사는 문장에서 없어도 되는 수식 성분입니다. 주로 완벽한 절 앞뒤, be동사+p.p. 사이, 조동사+동사원형 사이 등 틈새 자리를 비집고 들어가 동작을 수식합니다. 동사/형용사/다른 부사 수식 짝꿍을 찾으세요!" if usage == "adverb" else
                "💡 **일타강사 실전 압축 팁** | 명사는 문장의 주어, 목적어, 보어 자리뿐만 아니라 전치사의 목적어(전치사 뒤)와 명사+명사(복합명사) 형태의 출제가 잦습니다. 단어의 뜻과 함께 앞뒤 전치사와의 짝을 반드시 확인하세요!"
            )


        meaning_id = f"numbered-vocab-meaning-{number:04d}-{stable_id(term, answer)}"
        meaning_choices = stable_choices_by_usage(answer, usage, entries, "answer", meaning_id)
        
        # 뜻 맞추기 문제용 빈칸 만들기
        if has_smart:
            blank_meaning_sentence = meaning_sentence.replace(term, "_____", 1)
            # 만약 대소문자 문제로 치환 안됐을 때를 대비한 2차 치환
            if "_____" not in blank_meaning_sentence:
                blank_meaning_sentence = re.sub(re.escape(term), "_____", meaning_sentence, count=1, flags=re.IGNORECASE)
        else:
            blank_meaning_sentence = f"{term} = _____"

        # 1. 단어 뜻 맞추기 문제 (meaning)
        items.append({
            **base,
            "id": meaning_id,
            "questionType": "meaning",
            "contextId": f"numbered-vocab-{number:04d}",
            "answer": answer,
            "choices": meaning_choices,
            "answerIndex": meaning_choices.index(answer),
            "sentence": meaning_sentence,
            "sentenceKo": meaning_sentence_ko,
            "blankSentence": blank_meaning_sentence,
            "grammarNote": f"{numbered_vocab_note(entry, 'meaning', meaning_choices, entries, has_smart)}\n\n💡 **실전 적용 문맥**\n{custom_note}",
            "prompt": f"{number}번 단어 {term}의 뜻은?",
        })

        # 2. 뜻에 해당하는 영어 단어 맞추기 문제 (term)
        term_id = f"numbered-vocab-term-{number:04d}-{stable_id(answer, term)}"
        term_choices = stable_choices_by_usage(term, usage, entries, "term", term_id)
        
        if has_smart:
            blank_term_sentence = meaning_sentence.replace(term, "_____", 1)
            if "_____" not in blank_term_sentence:
                blank_term_sentence = re.sub(re.escape(term), "_____", meaning_sentence, count=1, flags=re.IGNORECASE)
        else:
            blank_term_sentence = f"{term} = _____"

        items.append({
            **base,
            "id": term_id,
            "questionType": "term",
            "contextId": f"numbered-vocab-{number:04d}",
            "answer": term,
            "choices": term_choices,
            "answerIndex": term_choices.index(term),
            "sentence": meaning_sentence,
            "sentenceKo": meaning_sentence_ko,
            "blankSentence": blank_term_sentence,
            "grammarNote": f"{numbered_vocab_note(entry, 'term', term_choices, entries, has_smart)}\n\n💡 **실전 적용 문맥**\n{custom_note}",
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
        usage = item.get("usage")
        if not usage or usage == "vocabulary":
            usage = infer_usage_from_meaning(term, answer)

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
            "grammarFocus": usage,
            "grammarNote": vocab_grammar_note(term, answer, usage, choices, vocab_entries),
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


def build_grammar_core_items() -> list[dict]:
    raw_data = [
        # === 1. 접속사 (Conjunction) ===
        {
            "num": 1,
            "type": "conjunction",
            "term": "Although",
            "sentence": "Although the marketing campaign was highly successful, sales did not meet the quarterly projections.",
            "sentenceKo": "마케팅 캠페인은 대단히 성공적이었지만, 매출은 분기 예상을 충족시키지 못했다.",
            "blankSentence": "_____ the marketing campaign was highly successful, sales did not meet the quarterly projections.",
            "choices": ["Although", "Despite", "However", "Moreover"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "빈칸 뒤에 주어(the marketing campaign)와 동사(was)가 있는 완전한 절이 오고, 두 절의 양보/대조 관계를 연결해야 하므로 부사절 접속사가 와야 합니다.",
            "wrongs": "Despite는 전치사라 뒤에 명사구가 와야 하고, However와 Moreover는 접속부사라 두 절을 직접 쉼표로 연결하지 못합니다.",
            "tip": "Although(접속사) vs Despite(전치사)의 절/명사구 구분법은 매달 출제되는 토익 핵심 출제 1순위 포인트입니다."
        },
        {
            "num": 2,
            "type": "conjunction",
            "term": "unless",
            "sentence": "The conference attendees will not receive their certificates unless they submit the feedback form by Friday.",
            "sentenceKo": "컨퍼런스 참가자들은 금요일까지 피드백 양식을 제출하지 않으면 수료증을 받지 못할 것이다.",
            "blankSentence": "The conference attendees will not receive their certificates _____ they submit the feedback form by Friday.",
            "choices": ["if", "unless", "without", "except"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "문맥상 '~하지 않으면 수료증을 받지 못한다'는 부정이 함축된 조건의 뜻이 되어야 하므로 조건 접속사 unless가 정답입니다.",
            "wrongs": "if를 넣으면 '제출하면 받지 못한다'가 되어 논리상 모순이며, without과 except는 뒤에 명사구가 와야 하는 전치사입니다.",
            "tip": "unless는 'if not'의 축약으로, 주절의 부정어(will not receive)와 호응하여 부정적 조건을 완성하는 경우가 많습니다."
        },
        {
            "num": 3,
            "type": "conjunction",
            "term": "so that",
            "sentence": "The department manager redesigned the work schedules so that employees could manage their tasks more efficiently.",
            "sentenceKo": "부서장은 직원들이 업무를 더 효율적으로 관리할 수 있도록 근무 일정을 재조정했다.",
            "blankSentence": "The department manager redesigned the work schedules _____ employees could manage their tasks more efficiently.",
            "choices": ["in order to", "so that", "because of", "rather than"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "빈칸 뒤에 절(employees could manage...)이 이어지며, 부서장이 일정을 조정한 '목적(~할 수 있도록)'을 연결해주는 부사절 접속사 so that이 필요합니다.",
            "wrongs": "in order to는 목적의 뜻이지만 뒤에 동사원형이 와야 하고, because of와 rather than은 전치사이므로 뒤에 절이 오지 못합니다.",
            "tip": "so that 뒤에는 조동사(can, could, may, might)가 동반되어 목적 의미를 부각시키는 경향이 큽니다."
        },
        {
            "num": 4,
            "type": "conjunction",
            "term": "Once",
            "sentence": "Once the contract is signed by both parties, we will begin the initial phase of the construction project.",
            "sentenceKo": "양측이 계약서에 서명하면 즉시, 우리는 건설 프로젝트의 초기 단계를 시작할 것이다.",
            "blankSentence": "_____ the contract is signed by both parties, we will begin the initial phase of the construction project.",
            "choices": ["Once", "While", "Already", "During"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "서명 완료 직후 건설을 시작한다는 시간적 선후 관계('일단 ~하면, ~하자마자')를 뜻하는 접속사 Once가 필요합니다.",
            "wrongs": "While은 행동의 동시성을 나타내어 어색하고, During은 전치사, Already는 단독 부사라 절을 연결할 수 없습니다.",
            "tip": "Once가 시간 부사절 접속사로 쓰일 때는 절의 동사가 현재시제(is signed)로 미래시를 대용하고, 주절에 미래시(will begin)가 옵니다."
        },
        {
            "num": 5,
            "type": "conjunction",
            "term": "While",
            "sentence": "While Ms. Chen was out of the office on business, her assistant handled all urgent inquiries.",
            "sentenceKo": "Ms. Chen 씨가 출장으로 사무실을 비운 동안, 그녀의 조수가 모든 긴급한 문의 사항들을 처리했다.",
            "blankSentence": "_____ Ms. Chen was out of the office on business, her assistant handled all urgent inquiries.",
            "choices": ["During", "While", "Meanwhile", "Besides"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "Ms. Chen이 자리를 비운 사건과 조수가 문의를 처리한 사건이 동시에 진행됨('~하는 동안')을 나타내는 접속사 While이 필요합니다.",
            "wrongs": "During은 전치사라 뒤에 명사구가 와야 하며, Meanwhile은 부사이고, Besides는 전치사/부사로 문맥상 부적절합니다.",
            "tip": "While은 접속사로서 뒤에 'S+V'를, During은 전치사로서 뒤에 특정 기간을 나타내는 '명사구'를 동반합니다."
        },
        {
            "num": 6,
            "type": "conjunction",
            "term": "whether",
            "sentence": "The human resources director will decide whether the internship program should be extended next year.",
            "sentenceKo": "인사 이사는 내년에 인턴십 프로그램을 연장할지 여부를 결정할 것이다.",
            "blankSentence": "The human resources director will decide _____ the internship program should be extended next year.",
            "choices": ["if", "whether", "that", "what"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "decide 동사의 목적어 역할을 하는 명사절 자리이며, 내용상 '연장할지 아닐지 여부'를 뜻하므로 whether가 가장 어울립니다.",
            "wrongs": "if도 명사절을 이끌 수 있으나, 문장 맨 뒤에 'or not'이 생략된 형태의 명시적 선택 구조나 격식체 목적어절에는 whether가 압도적으로 우선합니다.",
            "tip": "whether 명사절은 주어, 목적어, 보어 자리 및 전치사의 목적어 자리에도 올 수 있는 반면, 명사절 if는 전치사 뒤나 주어 자리에는 올 수 없습니다."
        },
        {
            "num": 7,
            "type": "conjunction",
            "term": "so",
            "sentence": "The printer was out of order, so the administrative assistant had to use the one in the lobby.",
            "sentenceKo": "프린터가 고장 나서, 행정 조수는 로비에 있는 프린터를 사용해야만 했다.",
            "blankSentence": "The printer was out of order, _____ the administrative assistant had to use the one in the lobby.",
            "choices": ["because", "so", "although", "but"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "프린터가 고장 난 것이 원인이고 로비 프린터를 사용한 것이 결과이므로, 쉼표(,) 뒤에서 순접의 인과관계를 만드는 등위접속사 so가 정답입니다.",
            "wrongs": "because를 넣으면 인과관계가 반대로 꼬이게 되고, although와 but은 의미상 대조 관계라 적절하지 않습니다.",
            "tip": "등위접속사 so는 앞절의 결과를 이어주는 구문으로만 쓰이며, 종속접속사와 달리 문장 맨 앞으로 갈 수 없습니다."
        },
        {
            "num": 8,
            "type": "conjunction",
            "term": "Since",
            "sentence": "Since the corporate server will be offline for maintenance, all employees should work locally.",
            "sentenceKo": "회사 서버가 점검을 위해 오프라인 상태가 될 것이기 때문에, 모든 직원들은 로컬로 작업해야 한다.",
            "blankSentence": "_____ the corporate server will be offline for maintenance, all employees should work locally.",
            "choices": ["Due to", "Since", "Therefore", "Furthermore"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "문장 처음에 위치하여 뒤의 원인 부사절(server will be offline...)과 주절의 결과를 이어주는 접속사 Since(~때문에)가 와야 합니다.",
            "wrongs": "Due to는 전치사이므로 절을 이끌 수 없으며, Therefore와 Furthermore는 접속부사로 단독 쉼표 수식만 가능합니다.",
            "tip": "Since는 '이래로(시간)'뿐만 아니라 '때문에(이유)'라는 뜻으로 토익 Part 5에서 because/as의 동의어로 아주 자주 출제됩니다."
        },
        {
            "num": 9,
            "type": "conjunction",
            "term": "either",
            "sentence": "Clients can choose to pay either by credit card or through bank transfer.",
            "sentenceKo": "고객들은 신용카드로 결제하거나 은행 송금을 통해 결제하는 것 중 하나를 선택할 수 있다.",
            "blankSentence": "Clients can choose to pay _____ by credit card or through bank transfer.",
            "choices": ["neither", "both", "either", "not only"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "빈칸 뒤의 상관 전치사구 or와 짝을 이루어 'A 또는 B 중 하나'를 완성하는 상관접속사 either가 정답입니다.",
            "wrongs": "both는 and, neither는 nor, not only는 but also와 함께 결합해야 하므로 뒤의 or와 짝이 맞지 않습니다.",
            "tip": "상관접속사 문제(both A and B, either A or B, neither A nor B)는 빈칸 뒤의 대구 형태(or/nor/and)를 보고 0.5초 만에 푸는 팁이 있습니다."
        },
        {
            "num": 10,
            "type": "conjunction",
            "term": "As soon as",
            "sentence": "As soon as the laboratory results are available, the research team will publish their final report.",
            "sentenceKo": "실험 결과가 나오는 대로 즉시, 연구팀은 최종 보고서를 발표할 것이다.",
            "blankSentence": "_____ the laboratory results are available, the research team will publish their final report.",
            "choices": ["As soon as", "Shortly", "Upon", "Immediate"],
            "prompt": "빈칸에 들어갈 가장 알맞은 접속사는?",
            "reason": "빈칸 뒤의 주어와 동사를 갖춘 부사절을 이끌면서 '~하자마자, ~하는 대로 즉시'의 의미를 더해주는 접속사 As soon as가 정답입니다.",
            "wrongs": "Upon은 뒤에 명사(구)가 와야 하는 전치사이며, Shortly는 부사, Immediate는 형용사입니다.",
            "tip": "As soon as는 3단어로 이루어진 부사절 접속사로, 'Upon -ing'나 'On -ing' 전치사 구문과 같은 의미를 나타냅니다."
        },
        # === 2. 전치사 (Preposition) ===
        {
            "num": 11,
            "type": "preposition",
            "term": "within",
            "sentence": "All division managers must submit their annual budget requests within the next three weeks.",
            "sentenceKo": "모든 부서장들은 향후 3주 이내에 연간 예산 요청서를 제출해야 한다.",
            "blankSentence": "All division managers must submit their annual budget requests _____ the next three weeks.",
            "choices": ["within", "during", "by", "until"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "빈칸 뒤에 '향후 3주'라는 시간적 범위(기간)가 오고, '3주 이내에' 완료해야 하는 한계를 나타내므로 within이 정답입니다.",
            "wrongs": "by와 until은 특정 시점(금요일, 다음 주 등) 앞에 오며, during은 특정 사건/행사 기간(휴가, 회의 등) 앞에 와서 수치 기간과 어울리지 않습니다.",
            "tip": "within은 수치 기간(3 weeks, 10 days)과 가장 친한 전치사로 '기간 이내에' 완료됨을 나타냅니다."
        },
        {
            "num": 12,
            "type": "preposition",
            "term": "due to",
            "sentence": "The flight was delayed due to severe weather conditions at the departing airport.",
            "sentenceKo": "출발 공항의 악천후 때문에 비행기가 지연되었다.",
            "blankSentence": "The flight was delayed _____ severe weather conditions at the departing airport.",
            "choices": ["because", "due to", "owing", "thanks"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "빈칸 뒤에 명사구가 오고, 비행기 지연의 '이유(~ 때문에)'를 이끌어주는 전치사가 필요하므로 due to가 정답입니다.",
            "wrongs": "because는 접속사라 뒤에 절이 와야 하고, owing과 thanks는 뒤에 to가 누락되어 단독 전치사 역할을 하지 못합니다.",
            "tip": "because of, due to, owing to, on account of는 모두 명사구 앞에서 이유를 나타내는 필수 전치사 4인방입니다."
        },
        {
            "num": 13,
            "type": "preposition",
            "term": "Despite",
            "sentence": "Despite the steep rise in production costs, the company decided not to increase the retail prices.",
            "sentenceKo": "생산 비용의 급격한 상승에도 불구하고, 회사는 소비자가를 인상하지 않기로 결정했다.",
            "blankSentence": "_____ the steep rise in production costs, the company decided not to increase the retail prices.",
            "choices": ["Although", "Despite", "Whereas", "However"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "빈칸 뒤 명사구(the steep rise...) 앞에서 두 절의 모순적인 양보 관계('~에도 불구하고')를 맺어주는 전치사 Despite가 필요합니다.",
            "wrongs": "Although와 Whereas는 절을 이끄는 양보 접속사이며, However는 부사이므로 명사구 앞에 오지 못합니다.",
            "tip": "Despite와 in spite of는 전치사이고, Although, even though, though는 접속사라는 사실을 구분하는 문제는 거의 매회 출제됩니다."
        },
        {
            "num": 14,
            "type": "preposition",
            "term": "since",
            "sentence": "Mr. Garcia has served as the chief executive officer since the company’s restructuring in 2022.",
            "sentenceKo": "Garcia 씨는 2022년 회사의 구조조정 이후로 최고경영자(CEO)로 재직해 오고 있다.",
            "blankSentence": "Mr. Garcia has served as the chief executive officer _____ the company’s restructuring in 2022.",
            "choices": ["for", "during", "since", "from"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "주절의 시제가 현재완료(has served)이므로, 과거의 기점(restructuring) 이후 현재까지 계속을 나타내는 전치사 since가 정답입니다.",
            "wrongs": "for는 숫자를 포함한 기간, during은 사건 기간 앞에 오며, from은 현재완료의 짝으로 기간 시점을 구체적으로 잡지 못합니다.",
            "tip": "주절에 'have/has p.p.'가 있고 빈칸 뒤에 과거 시점 명사나 과거 동사절이 오면 100% since가 정답입니다."
        },
        {
            "num": 15,
            "type": "preposition",
            "term": "for",
            "sentence": "The new employee handbook is now available for download on the company intranet.",
            "sentenceKo": "새로운 직원 핸드북은 이제 회사 인트라넷에서 다운로드할 수 있다.",
            "blankSentence": "The new employee handbook is now available _____ download on the company intranet.",
            "choices": ["to", "for", "about", "by"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "available 형용사 뒤에서 용도나 목적을 수식하여 '다운로드를 위해 사용 가능함'이라는 의미를 완성해주는 전치사 for가 필요합니다.",
            "wrongs": "to는 명사 download와 바로 결합할 경우 방향성이나 대상이 어색하고, by는 행위자나 수단을 수식하므로 문맥에 맞지 않습니다.",
            "tip": "be available for + 명사 / be available to + 동사원형 패턴을 숙지하면 품사에 따른 전치사 선택이 매끄러워집니다."
        },
        {
            "num": 16,
            "type": "preposition",
            "term": "throughout",
            "sentence": "The safety procedures are strictly enforced throughout all manufacturing facilities.",
            "sentenceKo": "모든 제조 시설 전역에서 안전 절차가 엄격하게 준수된다.",
            "blankSentence": "The safety procedures are strictly enforced _____ all manufacturing facilities.",
            "choices": ["throughout", "between", "against", "under"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "빈칸 뒤 명사구가 공간 전체를 의미하며, '곳곳에, 전역에'의 뉘앙스를 완성해주는 전치사 throughout가 정답입니다.",
            "wrongs": "between은 둘 사이에 오며, against는 ~에 대항하여, under는 ~ 아래에/영향 아래에라는 뜻입니다.",
            "tip": "throughout는 공간(전역에)과 시간(내내)에 모두 쓰여 '전체'를 강조하는 유용한 전치사입니다."
        },
        {
            "num": 17,
            "type": "preposition",
            "term": "In addition to",
            "sentence": "In addition to his regular duties, Mr. Patel coordinates the monthly training workshops.",
            "sentenceKo": "정규 업무 외에도, Patel 씨는 매월 열리는 교육 워크숍을 조율한다.",
            "blankSentence": "_____ his regular duties, Mr. Patel coordinates the monthly training workshops.",
            "choices": ["Except", "Besides", "In addition to", "Apart"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "원래 담당하는 정규 업무에 더하여 워크숍 조율이라는 또 다른 업무를 추가한다는 문맥이므로 'In addition to'가 정답입니다.",
            "wrongs": "Except는 제외 의미이며, Apart는 뒤에 from이 붙어야 전치사가 되고, Besides는 단독으로 쓰이지만 이 문장의 정합성에선 In addition to가 정확합니다.",
            "tip": "In addition to, besides, along with는 모두 기존 명사에 대상을 '추가'할 때 사용하는 빈출 전치사구입니다."
        },
        {
            "num": 18,
            "type": "preposition",
            "term": "until",
            "sentence": "The construction of the new research facility will be suspended until further notice.",
            "sentenceKo": "새로운 연구 시설의 건설은 추후 통지가 있을 때까지 보류될 것이다.",
            "blankSentence": "The construction of the new research facility will be suspended _____ further notice.",
            "choices": ["by", "until", "within", "since"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "건설이 보류되는 상태가 추후 통지 기점까지 '계속 지속됨'을 의미하므로 계속 전치사 until이 정답입니다.",
            "wrongs": "by는 일회성 제출/마감 시점에 쓰이며, within은 기간 이내, since는 과거 기점 이래로라는 뜻입니다.",
            "tip": "until은 '동사 행동의 지속'(suspended, stay, wait)과 어울리고, by는 '일회성 완료'(submit, complete, deliver)와 어울립니다."
        },
        {
            "num": 19,
            "type": "preposition",
            "term": "regardless of",
            "sentence": "All requests for annual leave will be reviewed regardless of the employee's tenure.",
            "sentenceKo": "모든 연차 휴가 요청은 직원의 근속 기간과 상관없이 검토될 것이다.",
            "blankSentence": "All requests for annual leave will be reviewed _____ the employee's tenure.",
            "choices": ["instead of", "regardless of", "due to", "in case of"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "근속 기간의 길고 짧음의 영향에서 제외하고 모두 동등하게 검토한다는 의미이므로 '~와 관계없이, 상관없이'를 뜻하는 regardless of가 정답입니다.",
            "wrongs": "instead of는 ~ 대신에, due to는 ~ 때문에, in case of는 ~의 경우에 대비하여 라는 뜻입니다.",
            "tip": "regardless of는 토익 파트 5/6에서 혜택, 조건, 절차 등과 관련해 매우 단골로 출제되는 전치사입니다."
        },
        {
            "num": 20,
            "type": "preposition",
            "term": "with",
            "sentence": "Please handle the fragile laboratory equipment with extreme care during the experiments.",
            "sentenceKo": "실험 중에 깨지기 쉬운 실험 장비를 각별한 주의를 기울여 다루어 주십시오.",
            "blankSentence": "Please handle the fragile laboratory equipment _____ extreme care during the experiments.",
            "choices": ["by", "with", "in", "for"],
            "prompt": "빈칸에 들어갈 가장 알맞은 전치사는?",
            "reason": "동사 handle을 수식하며 '어떤 태도/주의를 가지고서' 행동해야 하는지 나타내므로 명사 care와 결합하여 부사구(조심히)를 만드는 전치사 with가 정답입니다.",
            "wrongs": "by는 행위 수단, in은 분야나 물리적 위치, for는 대상을 나타내므로 care와 짝이 맞지 않습니다.",
            "tip": "with + 추상명사는 부사 역할을 합니다. 예: with care (조심히), with ease (쉽게), with efficiency (효율적으로)."
        },
        # === 3. 시제 및 동사 형태 (Tense) ===
        {
            "num": 21,
            "type": "tense",
            "term": "submits",
            "sentence": "The supervisor will approve the travel reimbursement once the employee submits the original receipts.",
            "sentenceKo": "직원이 영수증 원본을 제출하면 부서장이 출장비 환급을 승인할 것이다.",
            "blankSentence": "The supervisor will approve the travel reimbursement once the employee _____ the original receipts.",
            "choices": ["submits", "will submit", "submitted", "submitting"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "시간의 부사절을 이끄는 접속사 once 뒤에선 주절이 미래(will approve) 시제이더라도 부사절 내부는 현재시제 submits가 미래시를 대신합니다.",
            "wrongs": "will submit은 부사절의 미래 시제 중복 금지 규칙에 위배되고, submitted는 과거시제, submitting은 완전한 동사형태가 아닙니다.",
            "tip": "시간과 조건의 부사절(when, as soon as, if, once 등) 안에서는 미래의 일일지라도 현재시제가 미래시제를 반드시 대신합니다."
        },
        {
            "num": 22,
            "type": "tense",
            "term": "announced",
            "sentence": "The board of directors announced a major merger with a European telecommunications firm yesterday.",
            "sentenceKo": "이사회는 어제 유럽 이동통신사와의 대규모 합병을 발표했다.",
            "blankSentence": "The board of directors _____ a major merger with a European telecommunications firm yesterday.",
            "choices": ["announces", "announced", "will announce", "has announced"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "문장 끝에 명확한 과거의 단서인 'yesterday'(어제)가 존재하므로 단순 과거형 동사인 announced가 정답입니다.",
            "wrongs": "announces는 현재시제, will announce는 미래시제이고, 현재완료(has announced)는 명확한 과거 단서 부사와 섞여 쓰일 수 없습니다.",
            "tip": "과거를 가리키는 부사(yesterday, ago, last year, in + 과거연도)는 현재완료(have p.p.) 시제와 절대 함께 쓰이지 않고 단순과거와 함께 쓰입니다."
        },
        {
            "num": 23,
            "type": "tense",
            "term": "was completed",
            "sentence": "The renovation of the main lobby was completed ahead of schedule, to the delight of the clients.",
            "sentenceKo": "메인 로비의 리모델링은 예정보다 일찍 완료되어 고객들의 기쁨을 자아냈다.",
            "blankSentence": "The renovation of the main lobby _____ ahead of schedule, to the delight of the clients.",
            "choices": ["completed", "was completed", "completes", "is completing"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "주어(The renovation)는 완료 동작을 당하는 '사물'이며, 문맥상 이미 일어난 일이므로 과거 시점이면서 수동 구조를 가진 was completed가 정답입니다.",
            "wrongs": "completed는 목적어가 없는 이 구조에서 능동이라 어색하며, completes와 is completing은 현재 능동이라 문법/의미가 맞지 않습니다.",
            "tip": "토익 동사 문제에서 빈칸 바로 뒤에 목적어 명사구가 없고 부사구만 나열된다면 '수동태(be + p.p.)'가 정답일 확률이 매우 높습니다."
        },
        {
            "num": 24,
            "type": "tense",
            "term": "be installed",
            "sentence": "The safety officer requested that fire extinguishers be installed in every department room.",
            "sentenceKo": "안전 요원은 모든 부서실에 소화기가 설치되어야 한다고 요구했다.",
            "blankSentence": "The safety officer requested that fire extinguishers _____ in every department room.",
            "choices": ["are installed", "be installed", "should have installed", "installed"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "제안/요구/요청 동사 request 뒤의 that절 내부에는 당위성 의미가 포함되어 `(should) + 동사원형` 구조가 오고, 소화기는 설치되는 것이므로 be installed가 정답입니다.",
            "wrongs": "are installed는 are가 동사원형이 아니라서 탈락이며, installed만 쓰면 조동사 생략 후 남은 원형이 아닌 과거동사 형태라 올 수 없습니다.",
            "tip": "suggest, recommend, request, insist, demand, order 등의 동사 뒤 that절의 동사 자리는 무조건 '동사원형' 혹은 'be'가 옵니다."
        },
        {
            "num": 25,
            "type": "tense",
            "term": "Had we known",
            "sentence": "Had we known about the scheduling conflict earlier, we would have adjusted the meeting time.",
            "sentenceKo": "우리가 일정 조율 충돌에 대해 더 일찍 알았더라면, 회의 시간을 조정했을 텐데.",
            "blankSentence": "_____ about the scheduling conflict earlier, we would have adjusted the meeting time.",
            "choices": ["Did we know", "Had we known", "If we know", "Were we known"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "주절의 'would have adjusted'를 통해 가정법 과거완료 구문임을 알 수 있고, if가 생략되어 조동사가 앞으로 도치된 Had we known이 정답입니다.",
            "wrongs": "Did we know는 일반 의문문 구조라 어색하고, If we know는 시제가 맞지 않으며, Were we known은 수동 형태라 목적어(about...) 관계가 풀리지 않습니다.",
            "tip": "가정법 과거완료(if S + had p.p., S + would/could have p.p.)에서 if가 지워지면 주어-동사 위치가 바뀌어 'Had + 주어 + p.p.'가 됩니다."
        },
        {
            "num": 26,
            "type": "tense",
            "term": "are being updated",
            "sentence": "The customer database records are being updated to improve service speed currently.",
            "sentenceKo": "현재 서비스 속도 향상을 위해 고객 데이터베이스 기록들이 업데이트되고 있다.",
            "blankSentence": "The customer database records _____ to improve service speed currently.",
            "choices": ["updates", "are updating", "are being updated", "have updated"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "주어 records(복수)가 업데이트를 당하는 대상이고, currently(현재) 부사와 호응하여 진행 중인 수동 행동을 나타내므로 진행 수동태인 are being updated가 정답입니다.",
            "wrongs": "updates는 단수형이고 능동, are updating과 have updated는 복수형이지만 주어가 사람이 아닌 사물이므로 능동 수식이 불가합니다.",
            "tip": "진행형 수동태는 'be + being + p.p.' 형태를 지니며, 지금 당장 진행되고 있는 수동 동작을 묘사할 때 씁니다."
        },
        {
            "num": 27,
            "type": "tense",
            "term": "has been researching",
            "sentence": "The chemical company has been researching new composite materials for the past five years.",
            "sentenceKo": "그 화학 회사는 지난 5년 동안 새로운 복합 소재를 연구해 오고 있다.",
            "blankSentence": "The chemical company _____ new composite materials for the past five years.",
            "choices": ["researches", "has been researching", "researched", "is researching"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "기간을 뜻하는 부사구 'for the past five years'(지난 5년 동안)는 과거부터 현재까지의 동작의 연장을 지시하므로 현재완료 진행형(has been researching)이 정답입니다.",
            "wrongs": "researches는 일반적 사실의 현재시제이고, researched는 과거완료가 아닌 단순 과거이며, is researching은 일시적 현재진행이라 긴 기간 연장을 표현하지 못합니다.",
            "tip": "'for the past/last + 숫자'는 과거부터 지금까지 해오고 있음을 나타내어 주절에 '현재완료(has/have p.p.)' 혹은 '현재완료 진행형'을 동반합니다."
        },
        {
            "num": 28,
            "type": "tense",
            "term": "will have finished",
            "sentence": "By the time the new CEO arrives next week, the team will have finished the department transition.",
            "sentenceKo": "다음 주 신임 CEO가 도착할 무렵에는, 팀은 부서 인수인계를 완료해 놓았을 것이다.",
            "blankSentence": "By the time the new CEO arrives next week, the team _____ the department transition.",
            "choices": ["finished", "will have finished", "has finished", "finishes"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "`By the time + 주어 + 현재동사`가 이끄는 조건 부사절은 미래의 특정 마감 기준을 뜻하고, 그 무렵에는 주절의 동작이 이미 끝났을 것이므로 미래완료(will have finished)가 정답입니다.",
            "wrongs": "finished는 단순과거, has finished는 현재완료이며, finishes는 미래 마감 상황의 결과와 호응하지 않습니다.",
            "tip": "'By the time S + 현재동사, S + will have p.p.'는 미래완료 시제의 가장 정형화된 토익 기출 공식입니다."
        },
        {
            "num": 29,
            "type": "tense",
            "term": "to have been completed",
            "sentence": "The structural inspection report appears to have been completed before the official audit started.",
            "sentenceKo": "구조 점검 보고서는 공식 감사가 시작되기 전에 이미 작성 완료된 것처럼 보인다.",
            "blankSentence": "The structural inspection report appears _____ before the official audit started.",
            "choices": ["to complete", "to have been completed", "completing", "to be completed"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "본동사(appears: 현재)가 나타내는 시점보다 '이전의 일(공식 감사 시작 전)'이며 보고서가 '완료된 것'이므로, 완료형 수동 부정사 to have been completed가 적절합니다.",
            "wrongs": "to complete와 completing은 능동형이며, to be completed는 본동사와 동일한 시점의 수동이라 이전 일어난 완료 사실을 나타내지 못합니다.",
            "tip": "to부정사의 완료 시제는 'to have p.p.' 형태이며, 본동사의 시간보다 '한 시제 앞선 과거의 일'을 수식할 때 씁니다."
        },
        {
            "num": 30,
            "type": "tense",
            "term": "Review",
            "sentence": "Review the safety guidelines carefully before operating the heavy machinery.",
            "sentenceKo": "중장비를 가동하기 전에 안전 지침을 주의 깊게 검토하십시오.",
            "blankSentence": "_____ the safety guidelines carefully before operating the heavy machinery.",
            "choices": ["Review", "Reviewing", "Reviewed", "To review"],
            "prompt": "빈칸에 들어갈 가장 알맞은 동사 형태는?",
            "reason": "쉼표 앞의 부사구/부사절과 함께 쓰이며 주어가 없이 문장이 처음 기동되고 있으므로, 명령을 이끄는 동사원형 Review가 정답입니다.",
            "wrongs": "Reviewing은 분사구문으로 쓰일 수 있으나 뒤의 목적어 연결 후 문장의 주동사가 남지 않게 되어 비문이 되며, Reviewed/To review는 명령문을 이끌 수 없습니다.",
            "tip": "문장 맨 앞 빈칸 뒤에 명사가 오고 쉼표 뒤에 본동사가 따로 없다면, 동사원형으로 시작하는 '명령문' 문제입니다."
        }
    ]

    items = []
    for raw in raw_data:
        number = raw["num"]
        qtype = raw["type"]
        answer = raw["term"]
        choices = raw["choices"]
        sentence = raw["sentence"]
        sentence_ko = raw["sentenceKo"]
        blank_sentence = raw["blankSentence"]
        
        # 일타강사 전용 해설 포맷팅
        grammar_note_text = (
            f"🏷️ **문법 분류** | {qtype.upper()} 문법\n\n"
            f"문제 해설 | {raw['reason']} 따라서 정답은 ({answer_letter(choices, answer)}) 입니다.\n\n"

            f"오답 분석 |\n"
            f"- **{choices[0]}** : {'정답' if choices[0] == answer else raw['wrongs']}\n"
            f"- **{choices[1]}** : {'정답' if choices[1] == answer else raw['wrongs']}\n"
            f"- **{choices[2]}** : {'정답' if choices[2] == answer else raw['wrongs']}\n"
            f"- **{choices[3]}** : {'정답' if choices[3] == answer else raw['wrongs']}\n\n"
            f"토익 포인트 | {raw['tip']}"
        )
        
        items.append({
            "id": f"grammar-core-{number:03d}-{stable_id(sentence, answer)}",
            "questionType": qtype,
            "term": answer,
            "termKey": normalize_space(answer).lower(),
            "contextId": f"grammar-core-{number:03d}",
            "answer": answer,
            "choices": choices,
            "answerIndex": choices.index(answer),
            "tags": ["rc", "part5", qtype],
            "source": "Grammar Core (Grammar Master)",
            "sourcePath": "scripts/build_part5_approved.py",
            "quality": "approved",
            "contextType": "sentence",
            "sentence": sentence,
            "sentenceKo": sentence_ko,
            "blankSentence": blank_sentence,
            "grammarFocus": qtype,
            "grammarNote": grammar_note_text,
            "prompt": raw["prompt"],
        })
    return items


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
    items.extend(build_grammar_core_items())
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
