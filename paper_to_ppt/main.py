from __future__ import annotations

import argparse
import html
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


MISSING = "原文未明确说明，当前 PDF 未提取到，需人工核对全文。"


@dataclass
class PaperDraft:
    pdf_path: Path
    title: str
    doi: str
    keywords: str
    brief_summary: str
    journal: str
    jcr: str
    cas: str
    why_study: str
    innovation: str
    key_experiments: str
    sample_size: str
    muscle_sampling: str
    omics: str
    conclusions: list[str]
    peer_inspiration: list[str]
    figure_advice: list[str]
    extracted_figures: list[Path]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = generate_ppt(Path(args.input), Path(args.output))
    print(f"PPT: {result['pptx']}")
    print(f"Summary: {result['summary']}")
    print(f"Figure notes: {result['figure_notes']}")
    print(f"Missing info report: {result['missing_report']}")
    print(f"Extracted figures: {result['figures_dir']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a group-meeting PPT scaffold from paper PDFs.")
    parser.add_argument("--input", required=True, help="Folder containing full-text PDF files.")
    parser.add_argument("--output", required=True, help="Output PPTX path.")
    return parser


def generate_ppt(input_dir: Path, output_path: Path) -> dict[str, Path]:
    input_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    root = output_path.parents[1] if output_path.parent.name == "output" else output_path.parent.parent
    figures_dir = root / "extracted_figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(input_dir.glob("*.pdf"))
    drafts = [build_paper_draft(pdf_path, figures_dir) for pdf_path in pdfs]
    if not drafts:
        drafts = [empty_paper_draft(input_dir)]

    write_pptx(output_path, drafts)
    summary_path = output_path.parent / "paper_summary.md"
    figure_notes_path = output_path.parent / "figure_notes.md"
    missing_report_path = output_path.parent / "missing_info_report.md"
    summary_path.write_text(render_summary(drafts), encoding="utf-8")
    figure_notes_path.write_text(render_figure_notes(drafts), encoding="utf-8")
    missing_report_path.write_text(render_missing_report(drafts), encoding="utf-8")
    return {
        "pptx": output_path,
        "summary": summary_path,
        "figure_notes": figure_notes_path,
        "missing_report": missing_report_path,
        "figures_dir": figures_dir,
    }


def build_paper_draft(pdf_path: Path, figures_dir: Path) -> PaperDraft:
    extracted_text = extract_pdf_text(pdf_path)
    title = infer_title(pdf_path, extracted_text)
    doi = infer_doi(extracted_text)
    figures = extract_pdf_images(pdf_path, figures_dir)
    return PaperDraft(
        pdf_path=pdf_path,
        title=title,
        doi=doi,
        keywords=MISSING,
        brief_summary=brief_summary_from_text(extracted_text),
        journal=MISSING,
        jcr=MISSING,
        cas=MISSING,
        why_study=MISSING,
        innovation=MISSING,
        key_experiments=MISSING,
        sample_size=sample_size_from_text(extracted_text),
        muscle_sampling=muscle_sampling_from_text(extracted_text),
        omics=omics_from_text(extracted_text),
        conclusions=[MISSING],
        peer_inspiration=[
            "先用全文确认研究问题、实验设计和关键图，再决定是否适合作为组会精讲。",
            "汇报时每页只讲一个重点，图像必须来自原文 PDF 或原文附件。",
        ],
        figure_advice=figure_advice_from_text(extracted_text),
        extracted_figures=figures,
    )


def empty_paper_draft(input_dir: Path) -> PaperDraft:
    return PaperDraft(
        pdf_path=input_dir,
        title="未检测到 PDF",
        doi=MISSING,
        keywords=MISSING,
        brief_summary="请先把全文 PDF 放入 paper_to_ppt/input_papers/ 后再运行。",
        journal=MISSING,
        jcr=MISSING,
        cas=MISSING,
        why_study=MISSING,
        innovation=MISSING,
        key_experiments=MISSING,
        sample_size=MISSING,
        muscle_sampling=MISSING,
        omics=MISSING,
        conclusions=[MISSING],
        peer_inspiration=["没有 PDF 时不能生成带原文 Figure 的组会 PPT。"],
        figure_advice=["请先提供全文 PDF。"],
        extracted_figures=[],
    )


def extract_pdf_text(pdf_path: Path) -> str:
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        pass
    try:
        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def extract_pdf_images(pdf_path: Path, figures_dir: Path) -> list[Path]:
    try:
        import fitz  # type: ignore
    except Exception:
        return []

    extracted: list[Path] = []
    try:
        doc = fitz.open(str(pdf_path))
        for page_index in range(len(doc)):
            for image_index, image in enumerate(doc[page_index].get_images(full=True), 1):
                xref = image[0]
                base_image = doc.extract_image(xref)
                extension = base_image.get("ext", "png")
                image_path = figures_dir / f"{pdf_path.stem}_page{page_index + 1}_image{image_index}.{extension}"
                image_path.write_bytes(base_image["image"])
                extracted.append(image_path)
    except Exception:
        return extracted
    return extracted


def infer_title(pdf_path: Path, text: str) -> str:
    for line in text.splitlines()[:20]:
        clean = re.sub(r"\s+", " ", line).strip()
        if 20 <= len(clean) <= 220 and not clean.lower().startswith(("abstract", "doi", "copyright")):
            return clean
    return pdf_path.stem.replace("_", " ").replace("-", " ")


def infer_doi(text: str) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", text)
    return match.group(0) if match else MISSING


def brief_summary_from_text(text: str) -> str:
    if not text.strip():
        return MISSING
    abstract_match = re.search(r"abstract\s+(.{120,1200}?)(?:\n\s*(?:keywords|introduction|methods)\b)", text, flags=re.I | re.S)
    if abstract_match:
        return compact(abstract_match.group(1), 420)
    return "当前 PDF 已读取到部分文本，但未稳定定位摘要段落；需人工核对全文后完善精简版摘要。"


def sample_size_from_text(text: str) -> str:
    patterns = [
        r"\bn\s*=\s*\d+(?:,\d{3})*\b",
        r"\b\d+(?:,\d{3})*\s+(?:participants|patients|adults|athletes|subjects|children|men|women|cases|controls|individuals|volunteers)\b",
        r"\b\d+(?:,\d{3})*\s+(?:studies|trials|articles)\b",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            if match not in found:
                found.append(match)
    return "、".join(found[:5]) if found else MISSING


def muscle_sampling_from_text(text: str) -> str:
    blob = normalize(text)
    matches = []
    for term, label in [
        ("muscle biopsy", "muscle biopsy"),
        ("vastus lateralis", "vastus lateralis/股外侧肌"),
        ("gastrocnemius", "gastrocnemius/腓肠肌"),
        ("soleus", "soleus/比目鱼肌"),
        ("quadriceps", "quadriceps/股四头肌"),
        ("skeletal muscle tissue", "skeletal muscle tissue/骨骼肌组织"),
    ]:
        if term in blob:
            matches.append(label)
    return " / ".join(matches) if matches else MISSING


def omics_from_text(text: str) -> str:
    blob = normalize(text)
    matches = []
    for term, label in [
        ("single-cell rna-seq", "single-cell RNA-seq"),
        ("scrna-seq", "scRNA-seq"),
        ("snrna-seq", "snRNA-seq"),
        ("rna-seq", "RNA-seq"),
        ("atac-seq", "ATAC-seq"),
        ("proteomics", "proteomics"),
        ("metabolomics", "metabolomics"),
        ("dna methylation", "DNA methylation"),
        ("chip-seq", "ChIP-seq"),
        ("spatial transcriptomics", "spatial transcriptomics"),
        ("multi-omics", "multi-omics"),
    ]:
        if term in blob and label not in matches:
            matches.append(label)
    return " / ".join(matches) if matches else MISSING


def figure_advice_from_text(text: str) -> list[str]:
    blob = normalize(text)
    if "meta-analysis" in blob or "systematic review" in blob:
        return ["forest plot", "subgroup analysis", "risk of bias", "sensitivity analysis"]
    if "randomized" in blob or "intervention" in blob:
        return ["study flow chart", "intervention design", "primary outcome figure", "adverse events"]
    if "cohort" in blob or "uk biobank" in blob or "nhanes" in blob:
        return ["cohort flow chart", "exposure definition", "risk model", "Kaplan-Meier curve", "forest plot", "subgroup analysis"]
    if "mouse" in blob or "mice" in blob or "rat" in blob or "mechanism" in blob:
        return ["model validation", "intervention effect", "tissue staining", "omics pathway", "mechanism summary figure"]
    return ["Graphical abstract", "Study design figure", "Main result figures", "Mechanism figures"]


def render_summary(drafts: list[PaperDraft]) -> str:
    lines = ["# 组会文献汇报 PPT 准备摘要", ""]
    for index, draft in enumerate(drafts, 1):
        lines.extend(
            [
                f"## {index}. {draft.title}",
                "",
                f"- PDF：{draft.pdf_path}",
                f"- DOI：{draft.doi}",
                f"- 精简版摘要：{draft.brief_summary}",
                f"- 样本量：{draft.sample_size}",
                f"- 肌肉取材方法：{draft.muscle_sampling}",
                f"- 测了哪些组学：{draft.omics}",
                f"- 重要结论：{'；'.join(draft.conclusions)}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def render_figure_notes(drafts: list[PaperDraft]) -> str:
    lines = [
        "# Figure notes",
        "",
        "原则：PPT 只能使用原文 PDF 或原文附件中的图片；不允许自己编造实验结果图。",
        "",
    ]
    for draft in drafts:
        lines.extend([f"## {draft.title}", ""])
        if draft.extracted_figures:
            for figure in draft.extracted_figures:
                lines.append(f"- 已提取：{figure}；需要人工核对 Figure 编号、出处、标题和 DOI。")
        else:
            lines.append("- 当前未稳定提取到原文 Figure；需要人工从 PDF 中裁剪或导出原图。")
        lines.append("- 建议优先检查：" + "、".join(draft.figure_advice))
        lines.append("- 若大图包含 Fig A/B/C，当前工具未自动拆分时，请人工裁剪，不要生成替代图。")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_missing_report(drafts: list[PaperDraft]) -> str:
    lines = ["# 缺失信息报告", ""]
    for draft in drafts:
        lines.extend([f"## {draft.title}", ""])
        for label, value in [
            ("英文题目", draft.title),
            ("中文题目", MISSING),
            ("关键词", draft.keywords),
            ("期刊名称", draft.journal),
            ("JCR 分区", draft.jcr),
            ("中科院分区", draft.cas),
            ("作者为什么开展这个研究", draft.why_study),
            ("创新点", draft.innovation),
            ("关键实验和数据", draft.key_experiments),
            ("样本量", draft.sample_size),
            ("肌肉取材方法", draft.muscle_sampling),
            ("测了哪些组学", draft.omics),
        ]:
            if value == MISSING:
                lines.append(f"- {label}：{MISSING}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_pptx(output_path: Path, drafts: list[PaperDraft]) -> None:
    slides: list[dict[str, Any]] = [
        {
            "title": "组会文献汇报 PPT 草稿",
            "bullets": [
                f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "本 PPT 仅作为汇报框架；Figure 必须从原文 PDF 或附件人工核对后使用。",
            ],
            "footer": "sports-lit-digest paper_to_ppt",
        }
    ]
    for draft in drafts:
        slides.extend(
            [
                {
                    "title": draft.title,
                    "bullets": [
                        f"DOI：{draft.doi}",
                        f"精简版摘要：{compact(draft.brief_summary, 220)}",
                        f"样本量：{draft.sample_size}",
                    ],
                    "footer": f"{draft.title} | DOI: {draft.doi}",
                },
                {
                    "title": "组会汇报 / PPT 准备信息",
                    "bullets": [
                        f"作者为什么开展这个研究？{draft.why_study}",
                        f"创新点：{draft.innovation}",
                        f"关键实验和数据：{draft.key_experiments}",
                        f"肌肉取材方法：{draft.muscle_sampling}",
                        f"测了哪些组学：{draft.omics}",
                    ],
                    "footer": f"{draft.title} | DOI: {draft.doi}",
                },
                {
                    "title": "PPT 可讲图建议",
                    "bullets": [
                        "当前工具不编造 Figure；若未提取到原图，请人工从 PDF 裁剪。",
                        "建议优先查看：" + "、".join(draft.figure_advice),
                        "每张图需说明：展示什么、对应实验设计、关键数据、对结论的作用。",
                    ],
                    "footer": f"{draft.title} | DOI: {draft.doi}",
                },
            ]
        )
    write_minimal_pptx(output_path, slides)


def write_minimal_pptx(output_path: Path, slides: list[dict[str, Any]]) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr("[Content_Types].xml", content_types_xml(len(slides)))
        pptx.writestr("_rels/.rels", package_rels_xml())
        pptx.writestr("ppt/presentation.xml", presentation_xml(len(slides)))
        pptx.writestr("ppt/_rels/presentation.xml.rels", presentation_rels_xml(len(slides)))
        for index, slide in enumerate(slides, 1):
            pptx.writestr(f"ppt/slides/slide{index}.xml", slide_xml(slide["title"], slide["bullets"], slide.get("footer", "")))


def content_types_xml(slide_count: int) -> str:
    overrides = "\n".join(
        f'<Override PartName="/ppt/slides/slide{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for index in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  {overrides}
</Types>'''


def package_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>'''


def presentation_rels_xml(slide_count: int) -> str:
    rels = "\n".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
        for index in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {rels}
</Relationships>'''


def presentation_xml(slide_count: int) -> str:
    ids = "\n".join(
        f'<p:sldId id="{255 + index}" r:id="rId{index}"/>'
        for index in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>{ids}</p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>'''


def slide_xml(title: str, bullets: list[str], footer: str) -> str:
    body = "\n".join(text_shape(2, bullet, 760000, 1450000 + index * 520000, 10600000, 420000, font_size=1700) for index, bullet in enumerate(bullets[:8]))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
    {text_shape(10, title, 620000, 420000, 10900000, 650000, font_size=2600, bold=True)}
    {body}
    {text_shape(90, footer, 620000, 6400000, 10900000, 240000, font_size=900)}
  </p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''


def text_shape(shape_id: int, text: str, x: int, y: int, cx: int, cy: int, *, font_size: int, bold: bool = False) -> str:
    safe = html.escape(compact(text, 180))
    bold_attr = ' b="1"' if bold else ""
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="TextBox {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
  <p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r><a:rPr lang="zh-CN" sz="{font_size}"{bold_attr}/><a:t>{safe}</a:t></a:r></a:p></p:txBody>
</p:sp>'''


def compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def normalize(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9%+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    raise SystemExit(main())
