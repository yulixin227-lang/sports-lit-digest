import tempfile
import unittest
import zipfile
from pathlib import Path

from paper_to_ppt.main import generate_ppt


class PaperToPptTests(unittest.TestCase):
    def test_generate_ppt_creates_scaffold_and_missing_reports_without_fabricating_figures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "input_papers"
            input_dir.mkdir()
            (input_dir / "example-paper.pdf").write_bytes(
                b"%PDF-1.4\n% minimal invalid fixture for extraction-failure path\n"
            )
            output_path = root / "output" / "group_meeting.pptx"

            result = generate_ppt(input_dir, output_path)

            self.assertTrue(result["pptx"].exists())
            self.assertTrue(zipfile.is_zipfile(result["pptx"]))
            self.assertTrue(result["summary"].exists())
            self.assertTrue(result["figure_notes"].exists())
            self.assertTrue(result["missing_report"].exists())

            figure_notes = result["figure_notes"].read_text(encoding="utf-8")
            missing_report = result["missing_report"].read_text(encoding="utf-8")

        self.assertIn("不允许自己编造", figure_notes)
        self.assertIn("人工", figure_notes)
        self.assertIn("原文未明确说明", missing_report)
        self.assertIn("肌肉取材方法", missing_report)
        self.assertIn("测了哪些组学", missing_report)


if __name__ == "__main__":
    unittest.main()
