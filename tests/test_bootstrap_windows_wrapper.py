import os
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WRAPPER_PATH = os.path.join(ROOT_DIR, "scripts", "bootstrap.ps1")
README_PATH = os.path.join(ROOT_DIR, "README.md")


class BootstrapWindowsWrapperTests(unittest.TestCase):
    def _read_wrapper(self) -> str:
        with open(WRAPPER_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def test_windows_wrapper_declares_param_block_before_executable_statements(self) -> None:
        with open(WRAPPER_PATH, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]

        first_code_line = next(line for line in lines if line.strip())
        self.assertEqual(first_code_line, "param(")

    def test_windows_wrapper_uses_wsl_backed_bootstrap_path(self) -> None:
        wrapper = self._read_wrapper()

        self.assertIn('$BootstrapUrl = "https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh"', wrapper)
        self.assertIn('Get-Command wsl.exe -ErrorAction SilentlyContinue', wrapper)
        self.assertIn('& wsl.exe -l -q 2>$null', wrapper)
        self.assertIn('$bootstrapCommand = "bash <(curl -fsSL $BootstrapUrl)"', wrapper)
        self.assertIn('& wsl.exe bash -lc $bootstrapCommand', wrapper)
        self.assertNotIn("winget", wrapper)
        self.assertNotIn("repo fork", wrapper)
        self.assertNotIn("scripts\\setup_auth.py", wrapper)
        self.assertNotIn("Preparing native Windows setup", wrapper)

    def test_windows_wrapper_mentions_manual_setup_when_wsl_is_unavailable(self) -> None:
        wrapper = self._read_wrapper()

        self.assertIn('$ManualSetupUrl = "https://github.com/aspain/git-sweaty#manual-setup-no-scripts"', wrapper)
        self.assertIn('Install WSL first, then re-run setup:', wrapper)
        self.assertIn('If you would rather avoid WSL troubleshooting, use manual setup instead:', wrapper)
        self.assertIn('If the WSL path keeps failing, use manual setup instead:', wrapper)

    def test_windows_wrapper_preserves_forwarded_setup_args(self) -> None:
        wrapper = self._read_wrapper()

        self.assertIn('[string[]]$SetupArgs', wrapper)
        self.assertIn('function Join-BashArgs', wrapper)
        self.assertIn('if ($null -ne $SetupArgs -and $SetupArgs.Count -gt 0)', wrapper)
        self.assertIn('$bootstrapCommand = "$bootstrapCommand $(Join-BashArgs $SetupArgs)"', wrapper)

    def test_readme_points_windows_quick_start_to_direct_wsl_command(self) -> None:
        with open(README_PATH, "r", encoding="utf-8") as f:
            readme = f.read()

        self.assertIn("### Windows (requires WSL)", readme)
        self.assertIn('wsl bash -lc "bash <(curl -fsSL https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh)"', readme)
        self.assertIn("If you would rather avoid WSL troubleshooting on Windows, use [Manual Setup (No Scripts)](#manual-setup-no-scripts).", readme)
        self.assertNotIn("does not require WSL", readme)
        self.assertNotIn("install them automatically with `winget`", readme)

    def test_readme_keeps_macos_linux_bootstrap_command_unchanged(self) -> None:
        with open(README_PATH, "r", encoding="utf-8") as f:
            readme = f.read()

        self.assertIn("### macOS / Linux", readme)
        self.assertIn("Run this in Terminal.", readme)
        self.assertIn("bash <(curl -fsSL https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh)", readme)


if __name__ == "__main__":
    unittest.main()
