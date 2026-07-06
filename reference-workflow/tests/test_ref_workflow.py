import unittest

from ref_workflow import (
    article_to_zotero_item,
    detect_identifier,
    extract_identifiers_from_text,
    find_item_in_payload_by_doi,
    find_item_in_payload_by_pmid,
    normalize_doi,
    pubmed_article_summary,
    to_json_output,
)


class ReferenceWorkflowTests(unittest.TestCase):
    def test_detect_identifier_prefers_pmid_for_digits(self):
        self.assertEqual(detect_identifier("23903748"), ("pmid", "23903748"))

    def test_detect_identifier_normalizes_doi_urls(self):
        self.assertEqual(
            detect_identifier("https://doi.org/10.1038/NATURE12373"),
            ("doi", "10.1038/nature12373"),
        )

    def test_normalize_doi_strips_prefixes(self):
        self.assertEqual(normalize_doi("DOI: 10.3390/jcm14248694"), "10.3390/jcm14248694")

    def test_extract_identifiers_from_text_preserves_unique_pubmed_and_doi_values(self):
        text = """
        ([PubMed](https://pubmed.ncbi.nlm.nih.gov/32179076/?utm_source=x))
        Duplicate PMID: https://pubmed.ncbi.nlm.nih.gov/32179076/
        DOI: https://doi.org/10.1016/j.exer.2020.108002.
        Another DOI: 10.1167/iovs.18-24428
        """

        self.assertEqual(
            extract_identifiers_from_text(text),
            ["32179076", "10.1016/j.exer.2020.108002", "10.1167/iovs.18-24428"],
        )

    def test_to_json_output_escapes_console_unsafe_unicode(self):
        text = to_json_output({"abstract": "9\u2009mK Hz"})
        self.assertIn("\\u2009", text)

    def test_pubmed_article_summary_normalizes_core_fields(self):
        article = {
            "pmid": "32179076",
            "title": "Corneal epithelial basement membrane: Structure, function and regeneration.",
            "year": "2020",
            "journal": "Experimental eye research",
            "doi": "https://doi.org/10.1016/J.EXER.2020.108002",
        }

        self.assertEqual(
            pubmed_article_summary(article),
            {
                "verified": True,
                "pmid": "32179076",
                "doi": "10.1016/j.exer.2020.108002",
                "title": "Corneal epithelial basement membrane: Structure, function and regeneration.",
                "year": "2020",
                "journal": "Experimental eye research",
            },
        )

    def test_find_item_in_payload_by_doi_uses_exact_doi_field(self):
        payload = [
            {"key": "NOPE", "data": {"DOI": "10.1000/other"}},
            {"key": "MATCH", "data": {"DOI": "https://doi.org/10.1038/NATURE12373"}},
        ]

        item = find_item_in_payload_by_doi(payload, "10.1038/nature12373")

        self.assertEqual(item["key"], "MATCH")

    def test_find_item_in_payload_by_doi_does_not_match_empty_doi(self):
        payload = [{"key": "EMPTY", "data": {"DOI": ""}}]

        self.assertIsNone(find_item_in_payload_by_doi(payload, ""))

    def test_find_item_in_payload_by_pmid_matches_extra_field(self):
        payload = [
            {"key": "NOPE", "data": {"extra": "PMID: 99999999"}},
            {"key": "MATCH", "data": {"extra": "PMID: 11406548\nPMCID: PMC123"}},
        ]

        item = find_item_in_payload_by_pmid(payload, "11406548")

        self.assertEqual(item["key"], "MATCH")

    def test_article_to_zotero_item_maps_pubmed_article(self):
        template = {
            "itemType": "journalArticle",
            "title": "",
            "creators": [{"creatorType": "author", "firstName": "", "lastName": ""}],
            "abstractNote": "",
            "publicationTitle": "",
            "volume": "",
            "issue": "",
            "pages": "",
            "date": "",
            "DOI": "",
            "url": "",
            "extra": "",
            "tags": [],
            "collections": [],
        }
        article = {
            "pmid": "23903748",
            "pmcid": "PMC4221854",
            "title": "Nanometre-scale thermometry in a living cell.",
            "abstract": "Sensitive probing of temperature variations.",
            "authors": [
                {"fore_name": "G", "last_name": "Kucsko"},
                {"fore_name": "P C", "last_name": "Maurer"},
            ],
            "journal": "Nature",
            "volume": "500",
            "issue": "7460",
            "pages": "54-8",
            "year": "2013",
            "month": "Aug",
            "doi": "10.1038/nature12373",
        }

        item = article_to_zotero_item(
            template,
            article,
            tags=["_MCP-test-to-delete", "verified"],
            collection_keys=["ABCD1234"],
        )

        self.assertEqual(item["title"], "Nanometre-scale thermometry in a living cell.")
        self.assertEqual(item["publicationTitle"], "Nature")
        self.assertEqual(item["date"], "2013 Aug")
        self.assertEqual(item["DOI"], "10.1038/nature12373")
        self.assertEqual(item["creators"][0]["lastName"], "Kucsko")
        self.assertEqual(item["creators"][1]["firstName"], "P C")
        self.assertEqual(item["tags"], [{"tag": "_MCP-test-to-delete"}, {"tag": "verified"}])
        self.assertEqual(item["collections"], ["ABCD1234"])
        self.assertIn("PMID: 23903748", item["extra"])
        self.assertIn("PMCID: PMC4221854", item["extra"])


if __name__ == "__main__":
    unittest.main()
