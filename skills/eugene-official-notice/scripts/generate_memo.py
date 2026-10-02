#!/usr/bin/env python3
"""
(업무연락) 문서 생성기
원본 서식: (업무연락)_그룹_투자심의위원회_상정_前_사전_검토절차_안내의_건v3.docx 를 그대로 재현.
다만 실제 업무연락은 "번호 항목"만이 아니라 소제목(번호 없는 굵은 제목) + 대시 불릿,
표, 별첨 목록 등 다양한 형태로 쓰이므로 `sections`를 블록 리스트로 두어 어떤 조합도
표현할 수 있게 한다.

사용법:
    python3 generate_memo.py <input.json> <output.docx> [logo.jpg]

input.json 스키마:
{
  "date": "2026. 04. 20",
  "sender": "그룹혁신부문 비전추진본부",
  "recipient": "각 사 기획부서장",
  "cc": "각 사 전략 담당 임원",                 # 선택. "참조: ..." 줄
  "title": "그룹 투자심의위원회 상정 前 사전 검토절차 안내의 건",

  # 도입부 — 문자열 하나 또는 문단 리스트. 배경/의도를 설명하는 문단과 요청 취지를
  # 밝히는 문단을 나눠 쓰면 요구만 늘어놓는 느낌 없이 읽힌다.
  "intro": ["... 산업 환경이 빠르게 변화하고 있습니다.",
            "이에 ... 아래와 같이 시행하고자 하오니 협조하여 주시기 바랍니다."],

  "sections": [
    # 번호 항목 (기존 "1. 2. 3." 스타일) — 순서대로 자동 번호가 매겨짐
    {"type": "numbered", "text": "적용 대상 : AI 기술 또는 데이터 활용이 포함된 투자 건",
     "items": [{"text": "데이터 구축, 플랫폼/인프라, 솔루션 도입, 컨설팅 등"}]},

    # 번호 없는 소제목(굵게) + 하위 항목 — 안내/시행 문서에서 흔한 형태
    {"type": "heading", "heading": "교육 시행 개요",
     "items": [
        {"text": "신청 대상: 전 계열사 직원"},
        {"text": "장소: 유진빌딩 16층 HRD 센터(예정)"},
        {"text": "송부처: 유진IT서비스 경영전략팀 신소연 과장", "emphasis": true},
        {"text": "본 과정은 실습 중심 과정으로 개인 노트북 지참이 필수입니다.",
         "aside": "필수 유료 계정: Anthropic社의 Claude(클로드), Pro 요금제 $20/월"}
     ]},

    # 표 — 과정 비교, 일정표 등 구조화된 데이터
    {"type": "table", "headers": ["구분", "기본 과정", "심화 과정"],
     "rows": [["학습 목표", "...", "..."], ["일정", "...", "..."]]},

    # 별첨/붙임 목록 — 어느 자리에 적어도 자동으로 본문 맨 끝(비고·맺음말 뒤)에 배치된다
    {"type": "attachments", "items": ["별첨 1. 교육 과정별 안내 자료", "별첨 2. 대상자 명단 양식"]}
  ],

  "notes": ["AI 관련 투자안은 투자심의 대상금액에 충족하지 않더라도 ... 사전협의가 가능"],  # 선택, 문서 최하단 ※

  # 맺음말(선택) — 협조 요청·감사 등 마무리 인사. 문자열 하나 또는 문단 리스트.
  # ※ 비고와 성격이 다르므로 인사말을 notes에 넣지 않는다.
  "outro": "각 사의 적극적인 협조를 부탁드립니다.",

  "ending": "signature",                       # "signature"(기본) | "kkeut"
  "closing": "그룹혁신부문 비전추진본부"          # ending == "signature"일 때만 사용, 생략 시 sender
}

본문·intro·outro·notes·item text 어디서든 **...** 로 감싼 구간은 굵게 렌더링된다
(기한·금액처럼 놓치면 안 되는 값 한두 곳에만 쓴다).

각 item(dict)의 필드:
  - text (필수)
  - emphasis (선택, bool): true면 "- " 대신 "▶ "로 굵게 강조 표시 (걸림 들여쓰기 없이 통짜 정렬)
  - aside (선택, str): 같은 불릿 안에서 줄을 바꿔 "※ ..."로 덧붙는 짧은 부기. 항목 자체와
    다른 성격의 참고사항(예: 비용/조건)을 그 항목 바로 아래에 붙일 때 쓴다. 문서 전체에
    적용되는 비고는 top-level "notes"를 쓴다.

내용을 채울 때는 정해진 틀에 기계적으로 욱여넣지 말고, 사람이 쓴 것처럼 각 내용에 맞는
section 종류·위치·위계를 판단해서 구성한다 (SKILL.md 참고).
"""
import json
import random
import re
import sys
import os
import unicodedata
import zipfile
import shutil
from datetime import datetime, timezone

from docx import Document
from docx.shared import Twips, Emu, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT_NAME = "맑은 고딕"

PAGE_W_T = 11906
PAGE_H_T = 16838
MARGIN_T = 1134
HEADER_T = 851
FOOTER_T = 992
USABLE_WIDTH_T = PAGE_W_T - 2 * MARGIN_T  # 한 줄에 실제로 쓸 수 있는 폭(트윕)

ITEM_INDENT_T = 440       # 발신/수신/제목, 번호 항목·소제목·별첨 — 공통 좌측 시작선
BLOCK_INDENT_T = 400      # 본문 도입부, "- 아 래 -"
SUB_INDENT_T = 600        # "-"/"▶" 하위 항목의 기호 시작선

# 걸림 들여쓰기(hanging indent) 폭 — 줄이 넘어갈 때 이어지는 줄이 앞머리 기호 밑으로
# 파고들지 않고 텍스트 시작선에 맞춰 정렬되도록, 기호의 폭만큼 잡아준다.
NUM_HANGING_T = 330       # "1. ", "※ ", "별첨 1. " (전각 1자 + 공백)
BULLET_HANGING_T = 220    # "- "
EMPH_HANGING_T = 330      # "▶ "

LOGO_WIDTH = Emu(1495425)
LOGO_HEIGHT = Emu(365104)

# 11pt 맑은 고딕 기준, 전각(한글 등)/반각(영문·숫자·공백) 글자폭 근사치(트윕).
FULL_CHAR_W = 220
HALF_CHAR_W = 110
WRAP_SAFETY = 0.92  # 폰트 메트릭 근사치 오차를 감안한 여유분


def normalize_colon(text):
    """라벨 뒤 클론(:)은 앞말에 붙이고 뒤만 띄운다.
        "조사 대상 : 그룹 전 계열사" → "조사 대상: 그룹 전 계열사"
    앞뒤에 공백이 없는 클론("15:00~17:00", "https://")은 건드리지 않는다."""
    return re.sub(r" +: ", ": ", text)


def char_width(ch):
    return FULL_CHAR_W if unicodedata.east_asian_width(ch) in ("W", "F", "A") else HALF_CHAR_W


def estimate_line_count(text, avail_twips):
    """docProps 통계(Lines)용 근사치일 뿐, 실제 줄바꿈에는 쓰지 않는다.
    실제 줄바꿈은 원본 문서와 동일하게 Word 자체의 자동 줄바꿈에 맡긴다
    (직접 계산해 강제 개행을 넣으면 폰트 메트릭 오차로 부자연스럽게 잘린다)."""
    budget = avail_twips * WRAP_SAFETY
    width = sum(char_width(c) for c in text)
    return max(1, -(-width // budget)) if budget > 0 else 1


def set_font(run, size_pt, bold=False, underline=False, name=FONT_NAME):
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.underline = underline
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rFonts = rpr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rpr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), name)


BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def strip_bold_marks(text):
    return BOLD_RE.sub(r"\1", text)


def add_runs(p, text, size_pt, bold=False, underline=False):
    """문장 안의 **...** 구간만 굵게 넣는다. 마크가 없으면 통짜 run 하나와 동일하다."""
    pos = 0
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            set_font(p.add_run(text[pos:m.start()]), size_pt, bold=bold, underline=underline)
        set_font(p.add_run(m.group(1)), size_pt, bold=True, underline=underline)
        pos = m.end()
    if pos < len(text) or pos == 0:
        set_font(p.add_run(text[pos:]), size_pt, bold=bold, underline=underline)


def base_paragraph(doc, line_spacing=1.2, space_after=0, alignment=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = line_spacing
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(0)
    if alignment is not None:
        pf.alignment = alignment
    return p


class Stats:
    """docProps/app.xml에 쓸 Words/Characters/Lines/Paragraphs 등을 실측치로 채우기 위한 누적기."""
    def __init__(self):
        self.words = 0
        self.chars = 0
        self.chars_with_spaces = 0
        self.lines = 0
        self.paragraphs = 0

    def add(self, text, n_lines):
        self.words += len(text.split())
        self.chars += len(text.replace(" ", ""))
        self.chars_with_spaces += len(text)
        self.lines += n_lines
        self.paragraphs += 1


def add_text_paragraph(doc, stats, text, size_pt=11, bold=False, underline=False,
                        alignment=None, left_indent_t=0, hanging_t=0, normalize=True):
    """hanging_t를 주면 앞머리 기호("1. ", "- ", "※ ")의 폭만큼 걸림 들여쓰기를 걸어,
    줄이 넘어갈 때 이어지는 줄이 기호 밑이 아니라 텍스트 시작선에 정렬되게 한다.
    normalize=False는 이미 정규화된 문자열을 그대로 두어야 할 때 쓴다."""
    if normalize:
        text = normalize_colon(text)
    p = base_paragraph(doc, alignment=alignment)
    pf = p.paragraph_format
    eff_left = left_indent_t + hanging_t
    if eff_left:
        pf.left_indent = Twips(eff_left)
    if hanging_t:
        pf.first_line_indent = Twips(-hanging_t)

    avail = USABLE_WIDTH_T - eff_left

    add_runs(p, text, size_pt, bold=bold, underline=underline)

    plain = strip_bold_marks(text)
    stats.add(plain, estimate_line_count(plain, avail))
    return p


def append_aside(doc, stats, p, aside_text, size_pt=11):
    """같은 항목의 불릿 안에서 줄을 바꿔 '※ ...' 부기를 덧붙인다.
    (긴 문장의 자동 줄바꿈과는 무관한, 항목 하나에 딸린 의도적인 단일 개행이다.)"""
    text = normalize_colon(aside_text if aside_text.lstrip().startswith("※") else f"※ {aside_text}")
    br_run = p.add_run()
    br_run.add_break()
    set_font(br_run, size_pt)
    add_runs(p, text, size_pt)
    stats.add(strip_bold_marks(text), 1)


def add_spacer(doc, size_pt=5):
    p = base_paragraph(doc, line_spacing=1.0, space_after=0)
    r = p.add_run("")
    set_font(r, size_pt)


def as_paragraphs(value):
    """intro/outro는 문자열 하나 또는 문단 리스트 둘 다 받는다."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def add_body_paragraphs(doc, stats, texts):
    """도입부/맺음말처럼 번호도 불릿도 없는 본문 문단들. 문단 사이에 여백을 둔다."""
    last_p = None
    for i, text in enumerate(texts):
        if i:
            add_spacer(doc, 3)
        last_p = add_text_paragraph(doc, stats, text, size_pt=11,
                                     left_indent_t=BLOCK_INDENT_T,
                                     alignment=WD_ALIGN_PARAGRAPH.LEFT)
    return last_p


def add_items(doc, stats, items):
    last_p = None
    for it in items:
        text = it["text"]
        if it.get("emphasis"):
            last_p = add_text_paragraph(doc, stats, f"▶ {text}", size_pt=11, bold=True,
                                         left_indent_t=SUB_INDENT_T, hanging_t=EMPH_HANGING_T,
                                         alignment=WD_ALIGN_PARAGRAPH.LEFT)
        else:
            line = text if text.lstrip().startswith("※") else f"- {text}"
            last_p = add_text_paragraph(doc, stats, line, size_pt=11,
                                         left_indent_t=SUB_INDENT_T, hanging_t=BULLET_HANGING_T,
                                         alignment=WD_ALIGN_PARAGRAPH.LEFT)
        aside = it.get("aside")
        if aside:
            append_aside(doc, stats, last_p, aside)
    return last_p


def set_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblPr.append(borders)


def set_table_indent(table, indent_t):
    tblPr = table._tbl.tblPr
    ind = OxmlElement("w:tblInd")
    ind.set(qn("w:w"), str(indent_t))
    ind.set(qn("w:type"), "dxa")
    tblPr.append(ind)


def fill_cell(cell, text, bold, col_width):
    cell.width = col_width
    p = cell.paragraphs[0]
    pf = p.paragraph_format
    pf.space_after = Pt(0)
    pf.space_before = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(normalize_colon(text))
    set_font(run, 10, bold=bold)


def add_table_block(doc, stats, block):
    headers = block.get("headers", [])
    rows = block.get("rows", [])
    ncols = len(headers) if headers else (len(rows[0]) if rows else 0)
    if ncols == 0:
        return

    table = doc.add_table(rows=0, cols=ncols)
    table.autofit = False
    set_table_borders(table)
    set_table_indent(table, ITEM_INDENT_T)
    col_width = Twips((USABLE_WIDTH_T - ITEM_INDENT_T) // ncols)

    if headers:
        row_cells = table.add_row().cells
        for cell, text in zip(row_cells, headers):
            fill_cell(cell, text, bold=True, col_width=col_width)
    for row in rows:
        row_cells = table.add_row().cells
        for cell, text in zip(row_cells, row):
            fill_cell(cell, str(text), bold=False, col_width=col_width)

    stats.paragraphs += 1


def add_section(doc, stats, block, number=None):
    if block["type"] == "numbered":
        add_text_paragraph(doc, stats, f"{number}. {block['text']}", size_pt=11,
                            left_indent_t=ITEM_INDENT_T, hanging_t=NUM_HANGING_T,
                            alignment=WD_ALIGN_PARAGRAPH.LEFT)
    elif block["type"] == "heading":
        add_text_paragraph(doc, stats, block["heading"], size_pt=11, bold=True,
                            left_indent_t=ITEM_INDENT_T, alignment=WD_ALIGN_PARAGRAPH.LEFT)
    return add_items(doc, stats, block.get("items", []))


def add_attachments_block(doc, stats, block):
    last_p = None
    for item in block.get("items", []):
        last_p = add_text_paragraph(doc, stats, item, size_pt=11,
                                     left_indent_t=ITEM_INDENT_T, hanging_t=NUM_HANGING_T,
                                     alignment=WD_ALIGN_PARAGRAPH.LEFT)
    return last_p


def build(spec, logo_path, out_path):
    doc = Document()
    stats = Stats()

    section = doc.sections[0]
    section.page_width = Twips(PAGE_W_T)
    section.page_height = Twips(PAGE_H_T)
    section.top_margin = Twips(MARGIN_T)
    section.bottom_margin = Twips(MARGIN_T)
    section.left_margin = Twips(MARGIN_T)
    section.right_margin = Twips(MARGIN_T)
    section.header_distance = Twips(HEADER_T)
    section.footer_distance = Twips(FOOTER_T)

    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = Pt(11)
    rpr = style.element.get_or_add_rPr()
    rFonts = rpr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rpr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), FONT_NAME)

    # 로고
    p = base_paragraph(doc, line_spacing=1.0)
    run = p.add_run()
    run.add_picture(logo_path, width=LOGO_WIDTH, height=LOGO_HEIGHT)

    # 제목 "업 무 연 락"
    add_text_paragraph(doc, stats, "업 무 연 락", size_pt=15, bold=True, underline=True,
                        alignment=WD_ALIGN_PARAGRAPH.CENTER)

    # 날짜
    add_text_paragraph(doc, stats, spec["date"], size_pt=12,
                        alignment=WD_ALIGN_PARAGRAPH.RIGHT)

    add_spacer(doc, 3)

    # 발신 / 수신 / (참조) / 제목
    add_text_paragraph(doc, stats, f"발신: {spec['sender']}", size_pt=11,
                        left_indent_t=ITEM_INDENT_T, alignment=WD_ALIGN_PARAGRAPH.LEFT,
                        normalize=True)
    add_text_paragraph(doc, stats, f"수신: {spec['recipient']}", size_pt=11,
                        left_indent_t=ITEM_INDENT_T, alignment=WD_ALIGN_PARAGRAPH.LEFT,
                        normalize=True)
    if spec.get("cc"):
        add_text_paragraph(doc, stats, f"참조: {spec['cc']}", size_pt=11,
                            left_indent_t=ITEM_INDENT_T, alignment=WD_ALIGN_PARAGRAPH.LEFT,
                            normalize=True)
    add_text_paragraph(doc, stats, f"제목: {spec['title']}", size_pt=11,
                        left_indent_t=ITEM_INDENT_T, alignment=WD_ALIGN_PARAGRAPH.LEFT,
                        normalize=True)

    add_spacer(doc, 5)

    # 본문 도입부 — 배경·의도를 설명하는 문단(들). 문자열 하나 또는 리스트 모두 가능.
    add_body_paragraphs(doc, stats, as_paragraphs(spec.get("intro")))

    add_spacer(doc, 5)

    # - 아 래 -
    add_text_paragraph(doc, stats, "– 아    래 –", size_pt=11,
                        left_indent_t=BLOCK_INDENT_T, alignment=WD_ALIGN_PARAGRAPH.CENTER)

    add_spacer(doc, 5)

    # sections: 번호 항목 / 소제목+불릿 / 표 / 별첨 등 어떤 조합도 순서대로 렌더링
    last_p = None
    number = 0
    prev_type = None
    # 별첨/붙임은 어느 자리에 적혀 있든 본문 맨 끝(비고·맺음말 뒤)으로 모아 배치한다.
    attachment_blocks = []
    for block in spec.get("sections", []):
        btype = block.get("type", "numbered")
        if btype == "attachments":
            attachment_blocks.append(block)
            continue

        # 최상위 섹션 사이에는 항상 여백을 둔다. 항목이 두 줄 이상으로 넘어갈 때
        # 섹션끼리 한 덩어리로 뭉쳐 읽히는 것을 막는다.
        if prev_type is not None:
            add_spacer(doc, 3)

        if btype == "numbered":
            number += 1
            last_p = add_section(doc, stats, block, number=number)
        elif btype == "heading":
            last_p = add_section(doc, stats, block)
        elif btype == "table":
            add_table_block(doc, stats, block)
            last_p = None

        prev_type = btype

    # 문서 하단 ※ 비고 — 번호 항목(1. 2. ...)과 같은 좌측 시작선에 맞춘다.
    for note in spec.get("notes", []):
        text = note if note.lstrip().startswith("※") else f"※ {note}"
        add_spacer(doc, 5)
        last_p = add_text_paragraph(doc, stats, text, size_pt=11, left_indent_t=ITEM_INDENT_T,
                                     hanging_t=NUM_HANGING_T, alignment=WD_ALIGN_PARAGRAPH.LEFT)

    # 맺음말 — 협조 요청·감사 등 마무리 인사. 도입부와 같은 본문 문단으로 둔다.
    outro = as_paragraphs(spec.get("outro"))
    if outro:
        add_spacer(doc, 5)
        last_p = add_body_paragraphs(doc, stats, outro)

    # 별첨/붙임 목록
    for block in attachment_blocks:
        add_spacer(doc, 5)
        last_p = add_attachments_block(doc, stats, block)

    ending = spec.get("ending", "signature")
    if ending == "kkeut":
        # 서명 블록 없이, 마지막 내용 줄 끝에 "  끝."을 덧붙여 문서를 마무리한다.
        if last_p is not None:
            run = last_p.add_run("  끝.")
            set_font(run, 11)
    else:
        add_spacer(doc, 5)
        # 서명 (발신 부서, 굵게 큰 글씨, 중앙)
        add_text_paragraph(doc, stats, spec.get("closing", spec["sender"]), size_pt=16,
                            bold=True, alignment=WD_ALIGN_PARAGRAPH.CENTER)

    # --- 문서 속성: python-docx 기본값("python-docx", 2013-12-23 등)이 그대로 남지 않도록
    #     일반 Word 문서와 구분되지 않는 값으로 채운다.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cp = doc.core_properties
    cp.author = "user"
    cp.last_modified_by = "user"
    cp.comments = ""
    cp.revision = 1
    cp.created = now
    cp.modified = now

    doc.save(out_path)
    _patch_app_xml(out_path, stats)


def _patch_app_xml(docx_path, stats):
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Template>Normal</Template>'
        f'<TotalTime>{random.randint(4, 45)}</TotalTime>'
        '<Pages>1</Pages>'
        f'<Words>{stats.words}</Words>'
        f'<Characters>{stats.chars}</Characters>'
        '<Application>Microsoft Office Word</Application>'
        '<DocSecurity>0</DocSecurity>'
        f'<Lines>{stats.lines}</Lines>'
        f'<Paragraphs>{stats.paragraphs}</Paragraphs>'
        '<ScaleCrop>false</ScaleCrop>'
        '<HeadingPairs><vt:vector size="2" baseType="variant">'
        '<vt:variant><vt:lpstr>제목</vt:lpstr></vt:variant>'
        '<vt:variant><vt:i4>1</vt:i4></vt:variant>'
        '</vt:vector></HeadingPairs>'
        '<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr></vt:lpstr></vt:vector></TitlesOfParts>'
        '<Company></Company>'
        '<LinksUpToDate>false</LinksUpToDate>'
        f'<CharactersWithSpaces>{stats.chars_with_spaces}</CharactersWithSpaces>'
        '<SharedDoc>false</SharedDoc>'
        '<HyperlinksChanged>false</HyperlinksChanged>'
        '<AppVersion>16.0000</AppVersion>'
        '</Properties>'
    )

    tmp_path = docx_path + ".tmp"
    with zipfile.ZipFile(docx_path, "r") as zin:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "docProps/app.xml":
                    data = app_xml.encode("utf-8")
                zout.writestr(item, data)
    shutil.move(tmp_path, docx_path)


def main():
    if len(sys.argv) < 3:
        print("usage: generate_memo.py <input.json> <output.docx> [logo.jpg]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    if len(sys.argv) >= 4:
        logo_path = sys.argv[3]
    else:
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "logo.jpg")

    with open(input_path, encoding="utf-8") as f:
        spec = json.load(f)

    build(spec, logo_path, output_path)
    print(f"생성 완료: {output_path}")


if __name__ == "__main__":
    main()
