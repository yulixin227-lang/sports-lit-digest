# paper_to_ppt 手动组会 PPT 工具

这个工具用于把你手动下载的全文 PDF 整理成组会文献汇报 PPT 草稿。它不会接入每日 GitHub Actions，也不会每天自动运行。

## 使用步骤

1. 把全文 PDF 放入：

```text
paper_to_ppt/input_papers/
```

2. 在项目根目录运行：

```bash
python -m paper_to_ppt.main --input paper_to_ppt/input_papers --output paper_to_ppt/output/group_meeting.pptx
```

3. 查看输出：

```text
paper_to_ppt/output/group_meeting.pptx
paper_to_ppt/output/paper_summary.md
paper_to_ppt/output/figure_notes.md
paper_to_ppt/output/missing_info_report.md
paper_to_ppt/extracted_figures/
```

## 重要规则

- PPT 里的图片必须来自原文 PDF 或原文附件。
- 不允许自己画实验结果图。
- 不允许编造 Figure、样本量、肌肉取材方法、组学类型、JCR 或中科院分区。
- 如果工具没有稳定提取到原文 Figure，会在 `figure_notes.md` 中提示“需要人工从 PDF 中裁剪或导出原图”。
- 如果大图包含 Fig A/B/C 而工具没有稳定拆分，请人工裁剪，不要生成替代图。
- 每张图最终都需要人工核对 Figure 编号、原文出处、论文题目和 DOI。

## 当前能力边界

当前版本优先生成可讲解的 PPT 框架、摘要、Figure 核对清单和缺失信息报告。PDF 文本和图片提取依赖本地环境可用的 PDF 库；如果没有成功提取，工具会保守写入“原文未明确说明，当前 PDF 未提取到，需人工核对全文”。

真正用于组会前，请人工打开全文 PDF，逐张核对原文 Figure，并把需要讲解的 Figure 或 panel 放入最终 PPT。
