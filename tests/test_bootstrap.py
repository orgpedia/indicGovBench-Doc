"""test_bootstrap.py — Unit test for leaderboard print and bootstrap CLI."""

import unittest
from pathlib import Path
from unittest.mock import patch

from indic_gov_bench.eval.engine import print_leaderboard
from indic_gov_bench.eval.bootstrap import main as bootstrap_main


class TestLeaderboardBootstrap(unittest.TestCase):
    def test_print_leaderboard_missing_db(self):
        # Should exit gracefully without exception when db is missing
        missing_db = Path("non_existent_workspace_dir/benchmark.db")
        with patch("builtins.print") as mock_print:
            print_leaderboard("default", missing_db)
            mock_print.assert_called()
            output = " ".join(str(call.args) for call in mock_print.call_args_list)
            self.assertIn("Database not found", output)

    @patch("sys.argv", ["bootstrap", "--db-path", "non_existent.db"])
    def test_bootstrap_cli_invocation(self):
        with patch("indic_gov_bench.eval.bootstrap.print_leaderboard") as mock_print_lb:
            bootstrap_main()
            mock_print_lb.assert_called_once_with(run_id="default", db_path=Path("non_existent.db"))


if __name__ == "__main__":
    unittest.main()
