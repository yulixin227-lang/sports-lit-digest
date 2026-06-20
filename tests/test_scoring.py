import unittest

from src.score_papers import score_paper


JOURNALS = {
    "journals": [
        {"name": "British Journal of Sports Medicine", "aliases": ["Br J Sports Med"], "priority": 30}
    ]
}

KEYWORDS = {
    "keywords": [
        {"term": "HIIT", "zh": "高强度间歇训练", "aliases": ["high-intensity interval training"], "weight": 1.0},
        {"term": "VO2max", "zh": "最大摄氧量", "aliases": ["maximal oxygen uptake"], "weight": 1.0},
        {"term": "cardiorespiratory fitness", "zh": "心肺适能", "aliases": [], "weight": 1.0},
        {"term": "exercise physiology", "zh": "运动生理学", "aliases": [], "weight": 1.0},
    ]
}

SCORING = {
    "weights": {"journal": 30, "article_type": 20, "method_quality": 20, "keyword_match": 20, "readability": 10},
    "journal": {"unknown_score": 0},
    "article_type": {
        "base_score": 8,
        "preferred": [{"term": "randomized controlled trial", "score": 20}],
        "downgrade": [{"term": "protocol", "penalty": 16}, {"term": "editorial", "penalty": 14}],
    },
    "method_quality": {
        "base_with_abstract": 4,
        "positive_terms": [
            {"term": "randomized", "points": 4},
            {"term": "controlled", "points": 3},
            {"term": "participants", "points": 2},
            {"term": "effect size", "points": 2},
        ],
        "negative_terms": [{"term": "protocol", "points": 8}],
        "sample_size_regex": "\\b(n\\s*=\\s*\\d+|\\d+\\s+(participants|patients|adults|athletes|subjects))\\b",
        "sample_size_points": 4,
    },
    "keyword_match": {"target_matches": 4},
    "readability": {
        "abstract_min_chars": 80,
        "abstract_full_score": 6,
        "abstract_partial_score": 3,
        "doi_points": 2,
        "structured_abstract_points": 2,
    },
}


class ScoringTests(unittest.TestCase):
    def test_high_quality_trial_scores_above_threshold(self):
        paper = {
            "title": "High-intensity interval training improves VO2max and cardiorespiratory fitness",
            "abstract": "METHODS: A randomized controlled trial included n=120 participants. RESULTS: HIIT improved maximal oxygen uptake with reported effect size.",
            "journal": "British Journal of Sports Medicine",
            "doi": "10.1000/example",
            "article_types": ["Randomized Controlled Trial"],
        }
        scored = score_paper(paper, JOURNALS, KEYWORDS, SCORING)
        self.assertGreaterEqual(scored["score"], 70)

    def test_protocol_is_downgraded(self):
        paper = {
            "title": "Protocol for a future HIIT study",
            "abstract": "This protocol describes exercise physiology and high-intensity interval training methods.",
            "journal": "British Journal of Sports Medicine",
            "doi": "10.1000/protocol",
            "article_types": ["Protocol"],
        }
        scored = score_paper(paper, JOURNALS, KEYWORDS, SCORING)
        self.assertLess(scored["score_breakdown"]["article_type"], 8)


if __name__ == "__main__":
    unittest.main()
