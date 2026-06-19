import types
from unittest.mock import patch

import pytest
import sys
import os

# Ensure the pipeline package path is on sys.path for tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import link_verifier


class DummyResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def test_orcid_high_confidence():
    html = """
    <html><head><title>Jane Q. Researcher - ORCID</title>
    <meta name='description' content='Jane Q. Researcher ORCID profile'>
    </head><body>
    <script type='application/ld+json'>{"@context":"http://schema.org","@type":"Person","name":"Jane Q. Researcher"}</script>
    </body></html>
    """

    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://orcid.org/0000-0000-0000-0000", "Jane Q. Researcher", "University of Nowhere")
        assert score > 0.7


def test_unrelated_page_rejected():
    html = "<html><head><title>About Widgets</title></head><body><p>No people here.</p></body></html>"
    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, _ = link_verifier.score_link("https://example.com/widgets", "John Smith", "Some University")
        assert score < 0.5


def test_jsonld_partial_match_boosts():
    html = """
    <html><head><title>J. Researcher</title></head>
    <body>
    <script type='application/ld+json'>{"@context":"http://schema.org","@type":"Person","name":"J Researcher","affiliation":"University of Nowhere"}</script>
    </body></html>
    """
    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://university.edu/people/jresearcher", "J Researcher", "University of Nowhere")
        assert score > 0.6


def test_verify_and_rank_prefers_highest():
    html_good = "<html><head><title>Dr Alice Johnson</title></head><body></body></html>"
    html_bad = "<html><head><title>Some Other Page</title></head><body></body></html>"

    def side_effect(url, headers=None, timeout=8, allow_redirects=True):
        if "good" in url:
            return DummyResp(html_good)
        return DummyResp(html_bad)

    with patch("link_verifier.requests.get", side_effect=side_effect):
        # use a lower threshold to reflect title-only boosts in this mocked case
        results = link_verifier.verify_and_rank(["https://good.example/good", "https://bad.example/bad"], "Alice Johnson", "SomeInst", threshold=0.2)
        assert len(results) == 1
        assert "good" in results[0]["url"]
