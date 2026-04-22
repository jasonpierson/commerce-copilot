from __future__ import annotations

from unittest import TestCase

from app.api.query_service import QueryService


class QueryServiceExtractionTests(TestCase):
    def setUp(self) -> None:
        self.service = QueryService()

    def test_extract_inventory_query_removes_article_and_punctuation(self) -> None:
        product = self.service._extract_inventory_query("Check inventory for the Phantom X shoes?")  # noqa: SLF001
        self.assertEqual(product, "Phantom X shoes")

    def test_extract_inventory_query_handles_stock_level_variant(self) -> None:
        product = self.service._extract_inventory_query("What is the stock level for the Nova hoodie.")  # noqa: SLF001
        self.assertEqual(product, "Nova hoodie")

    def test_extract_incident_code_returns_uppercase_code(self) -> None:
        incident_code = self.service._extract_incident_code("please summarize inc-1091 for me")  # noqa: SLF001
        self.assertEqual(incident_code, "INC-1091")

    def test_extract_incident_code_returns_none_when_missing(self) -> None:
        incident_code = self.service._extract_incident_code("summarize the checkout issue")  # noqa: SLF001
        self.assertIsNone(incident_code)
