"""Configuration must reject storage drivers that the application ignores."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from pydantic import ValidationError

from server.app.config import Settings
from server.app.services.clock import utc_from_timestamp_naive, utc_now_naive


class StorageConfigurationTests(unittest.TestCase):
    def test_unimplemented_storage_drivers_fail_validation(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, STORAGE_DRIVER="s3")


class MicroMindDefaultsTests(unittest.TestCase):
    def test_micromind_is_off_with_no_url_unless_env_opts_in(self):
        env = {k: v for k, v in os.environ.items() if k not in ("USE_MICROMIND", "MICROMIND_API_URL")}
        with patch.dict(os.environ, env, clear=True):
            cfg = Settings(_env_file=None)
        self.assertFalse(cfg.USE_MICROMIND)
        self.assertEqual(cfg.MICROMIND_API_URL, "")


class UTCClockTests(unittest.TestCase):
    def test_database_clock_returns_naive_utc_not_local_time(self):
        now = utc_now_naive()
        self.assertIsNone(now.tzinfo)
        self.assertLess(abs((datetime.now(timezone.utc).replace(tzinfo=None) - now).total_seconds()), 2)

    def test_unix_expiry_conversion_is_utc(self):
        converted = utc_from_timestamp_naive(0)
        self.assertEqual(converted, datetime(1970, 1, 1))
        self.assertIsNone(converted.tzinfo)


if __name__ == "__main__":
    unittest.main()