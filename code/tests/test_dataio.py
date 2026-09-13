"""Tests for the code.dataio package (loaders, fx conversion, blank-amount
resolution, and per-request joining)."""

from __future__ import annotations

import unittest

from code.dataio import build_rate_index, convert_amount, load_all
from code.dataio.join import build_request_bundle
from code.dataio.vision_stub import resolve_all_blank_amounts


class TestLoaders(unittest.TestCase):
    def test_load_all_row_counts(self):
        tables = load_all()
        self.assertEqual(len(tables["events"]), 25342)
        self.assertEqual(len(tables["profiles"]), 275)
        self.assertEqual(len(tables["requests"]), 250)
        self.assertEqual(len(tables["payment_options"]), 790)
        self.assertEqual(len(tables["exchange_rates"]), 134)
        self.assertEqual(len(tables["messages"]), 215)
        self.assertEqual(len(tables["images"]), 16)

    def test_blank_amounts_are_nan_not_zero(self):
        tables = load_all()
        self.assertEqual(tables["events"]["amount"].isna().sum(), 16)


class TestFx(unittest.TestCase):
    def setUp(self):
        tables = load_all()
        self.rate_index = build_rate_index(tables["exchange_rates"])

    def test_same_currency_passthrough(self):
        self.assertEqual(convert_amount(50, "INR", "INR", "2024-01-15", self.rate_index), 50.0)

    def test_direct_conversion(self):
        result = convert_amount(100, "EUR", "ZAR", "2023-10-15", self.rate_index)
        self.assertEqual(result, 2000.0)

    def test_inverse_conversion(self):
        result = convert_amount(100, "ZAR", "EUR", "2023-10-15", self.rate_index)
        self.assertEqual(result, 5.0)

    def test_missing_pair_raises(self):
        with self.assertRaises(ValueError):
            convert_amount(100, "EUR", "ZAR", "1999-01-01", self.rate_index)


class TestVisionStub(unittest.TestCase):
    def test_resolve_all_blank_amounts_fills_all_16(self):
        tables = load_all()
        resolved = resolve_all_blank_amounts(tables["events"], tables["images"])
        self.assertEqual(resolved["amount"].isna().sum(), 0)

    def test_resolve_does_not_mutate_input(self):
        tables = load_all()
        resolve_all_blank_amounts(tables["events"], tables["images"])
        self.assertEqual(tables["events"]["amount"].isna().sum(), 16)

    def test_known_event_10521_resolves_to_confirmed_amount(self):
        tables = load_all()
        resolved = resolve_all_blank_amounts(tables["events"], tables["images"])
        value = resolved.loc[resolved["event_id"] == "event_10521", "amount"].iloc[0]
        self.assertEqual(value, 393.22)


class TestJoin(unittest.TestCase):
    def test_build_request_bundle_request_113(self):
        bundle = build_request_bundle("request_113")
        self.assertGreater(len(bundle.events), 0)
        self.assertGreaterEqual(len(bundle.payment_options), 2)
        self.assertLessEqual(len(bundle.payment_options), 4)
        self.assertEqual(bundle.profile["user_id"], "user_113")

    def test_build_request_bundle_unknown_raises(self):
        with self.assertRaises(KeyError):
            build_request_bundle("request_01")

    def test_build_request_bundle_spot_sample(self):
        for request_id in ["request_113", "request_26", "request_27"]:
            bundle = build_request_bundle(request_id)
            self.assertIsNotNone(bundle.request)
            self.assertIsNotNone(bundle.profile)


if __name__ == "__main__":
    unittest.main()
