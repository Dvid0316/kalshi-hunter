import importlib.util
import unittest
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
spec = importlib.util.spec_from_file_location("picks_app_app", APP_PATH)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)


class DisplayMathTests(unittest.TestCase):
    def test_yes_side_payout_and_ev(self):
        # 40c YES, 70% estimate: 60c gross payout, 30c EV before the project fee.
        result = app_module.display_math("yes", 0.40, 0.70, 0.60, 0.80, qty=10)
        self.assertAlmostEqual(result["payout"], 0.60)
        self.assertAlmostEqual(result["p_win"], 0.70)
        self.assertAlmostEqual(result["ev"], 0.70 - 0.40 - result["fee"])
        self.assertAlmostEqual(result["ev_worst"], 0.60 - 0.40 - result["fee"])

    def test_no_side_reverses_price_and_probability(self):
        # 25c NO has 75c gross payout; NO probability is 1 - P(YES).
        result = app_module.display_math("no", 0.25, 0.20, 0.10, 0.30, qty=10)
        self.assertAlmostEqual(result["payout"], 0.75)
        self.assertAlmostEqual(result["p_win"], 0.80)
        self.assertAlmostEqual(result["ev"], 0.80 - 0.25 - result["fee"])
        self.assertAlmostEqual(result["ev_worst"], 0.70 - 0.25 - result["fee"])
        self.assertAlmostEqual(result["profit_if_win"], 0.75 - result["fee"])


if __name__ == "__main__":
    unittest.main()
