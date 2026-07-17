import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_windows_distribution_files_exist(self) -> None:
        expected = (
            "scripts/run_windows.ps1",
            "scripts/build_windows.ps1",
            "SpectrumRestore.spec",
            "README.md",
            "docs/使用与算法说明.md",
        )

        self.assertTrue(all((PROJECT_ROOT / item).is_file() for item in expected))

    def test_linux_launch_script_is_not_created(self) -> None:
        self.assertFalse((PROJECT_ROOT / "scripts/run_linux.sh").exists())

    def test_documentation_explains_hexadecimal_conversion(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        guide = (PROJECT_ROOT / "docs/使用与算法说明.md").read_text(encoding="utf-8")

        self.assertIn("012c", readme)
        self.assertIn("300", readme)
        self.assertIn("十六进制", guide)
        self.assertIn("十进制", guide)


if __name__ == "__main__":
    unittest.main()
