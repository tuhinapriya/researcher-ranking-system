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
        assert score >= 0.8


def test_semantic_scholar_author_high_confidence():
    html = """
    <html><head><title>Martin M. Hanczyc | Semantic Scholar</title>
    <meta name='description' content='Martin M. Hanczyc author page'>
    </head><body></body></html>
    """

    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://www.semanticscholar.org/author/2254644246", "Martin M. Hanczyc", "University of Warsaw")
        assert score >= 0.78


def test_google_scholar_search_high_confidence():
    html = """
    <html><head><title>Google Scholar</title>
    <meta name='description' content='Search results for Dan Boneh Stanford University quantum computing algorithms'>
    </head><body>Results for Dan Boneh</body></html>
    """

    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://scholar.google.com/scholar?q=Dan+Boneh+Stanford+University+quantum+computing+algorithms", "Dan Boneh", "Stanford University")
        assert score >= 0.8


def test_paperlantern_search_high_confidence():
    html = """
    <html><head><title>Paper Lantern search results</title>
    <meta name='description' content='Results for Monroe Kennedy Stanford University Robotics Dexterity'>
    </head><body>Paper Lantern results for Monroe Kennedy</body></html>
    """

    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://www.paperlantern.ai/search?q=Monroe+Kennedy+Stanford+University+Robotics+Dexterity", "Monroe Kennedy", "Stanford University")
        assert score >= 0.6


def test_wikipedia_search_high_confidence():
    html = """
    <html><head><title>Wikipedia Search Results</title>
    <meta name='description' content='Search results for Fei-Fei Li Stanford University'>
    </head><body>Search results</body></html>
    """

    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://en.wikipedia.org/w/index.php?search=Fei-Fei+Li+Stanford+University", "Fei-Fei Li", "Stanford University")
        assert score >= 0.52


def test_no_results_page_rejected():
    html = "<html><head><title>No results found</title></head><body>No results found.</body></html>"

    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://www.semanticscholar.org/search?q=Michael+Sony", "Michael Sony", "Namibia University of Science and Technology")
        assert score == 0.0
        assert details.get("negative_page") is True


def test_university_profile_high_confidence():
    html = """
    <html><head><title>Monroe Kennedy III | Stanford Profile</title>
    <meta name='description' content='Monroe Kennedy III is an assistant professor at Stanford'>
    </head><body></body></html>
    """

    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, details = link_verifier.score_link("https://profiles.stanford.edu/monroe-kennedy", "Monroe Kennedy III", "Stanford University")
        assert score >= 0.75


def test_unrelated_page_rejected():
    html = "<html><head><title>About Widgets</title></head><body><p>No people here.</p></body></html>"
    with patch("link_verifier.requests.get", return_value=DummyResp(html)):
        score, _ = link_verifier.score_link("https://example.com/widgets", "John Smith", "Some University")
        assert score < 0.5


def test_broken_google_scholar_rejected():
    with patch("link_verifier.requests.get", return_value=DummyResp("not found", status_code=404)):
        score, details = link_verifier.score_link("https://scholar.google.com/citations?user=k_t74JkAAAAJ", "Dan Boneh", "Stanford University")
        assert score == 0.0
        assert details.get("status_code") == 404


def test_science_gov_detector_page_rejected():
    html = "<html><head><title>Detector</title></head><body>Please wait while we verify you are human.</body></html>"

    resp = DummyResp(html)
    resp.url = "https://www.science.gov/detector"

    with patch("link_verifier.requests.get", return_value=resp):
        score, details = link_verifier.score_link("https://www.science.gov/scigov/desktop/en/search.html?originalPath=/search.html?fullRecord=Dan+Boneh", "Dan Boneh", "Stanford University")
        assert score == 0.0
        assert details.get("negative_page") is True


def test_baidu_scholar_captcha_page_rejected():
    html = "<html><head><title>Security check</title></head><body>captcha</body></html>"

    resp = DummyResp(html)
    resp.url = "https://wappass.baidu.com/static/captcha/index"

    with patch("link_verifier.requests.get", return_value=resp):
        score, details = link_verifier.score_link("https://xueshu.baidu.com/s?wd=Andrew+Ng+Stanford+University", "Andrew Ng", "Stanford University")
        assert score == 0.0
        assert details.get("negative_page") is True


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


def test_verify_and_rank_returns_all_high_confidence_links():
    html_good = "<html><head><title>Dr Alice Johnson</title></head><body></body></html>"
    html_second = "<html><head><title>Alice Johnson - Department Profile</title></head><body></body></html>"

    def side_effect(url, headers=None, timeout=8, allow_redirects=True):
        if "good" in url or "second" in url:
            return DummyResp(html_good)
        return DummyResp(html_good if "profile" in url else html_second)

    with patch("link_verifier.requests.get", side_effect=side_effect):
        results = link_verifier.verify_and_rank(
            ["https://good.example/good", "https://second.example/second"],
            "Alice Johnson",
            "SomeInst",
            threshold=0.2,
        )
        assert len(results) == 2
        assert results[0]["score"] >= results[1]["score"]
