import unittest
from pathlib import Path
from unittest.mock import patch

from indic_gov_bench.providers.batch_adapters.modal_adapter import ModalBatchAdapter
from indic_gov_bench.providers.modal_provider import call_modal_realtime


class TestModalProviders(unittest.TestCase):
    def test_modal_env_url_requirements(self):
        """Verifies that missing Modal endpoint environment variables raise clear ValueErrors."""
        adapter = ModalBatchAdapter(provider_slug="paddleocr_hpd")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as cm:
                adapter._get_client()
            self.assertIn("OCR_GATEWAY_URL", str(cm.exception))

            with self.assertRaises(ValueError) as cm:
                call_modal_realtime("tesseract", Path("dummy.pdf"))
            self.assertIn("TESSERACT_URL", str(cm.exception))

            with self.assertRaises(ValueError) as cm:
                call_modal_realtime("qwen", Path("dummy.pdf"))
            self.assertIn("QWEN_URL", str(cm.exception))

            with self.assertRaises(ValueError) as cm:
                call_modal_realtime("paddleocr_hpd", Path("dummy.pdf"))
            self.assertIn("HPD_URL", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
