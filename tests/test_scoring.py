import unittest

from src.score_papers import score_paper
from src.utils import ROOT, load_yaml_config


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
    "result_specificity": {
        "low_threshold": 50,
        "medium_threshold": 75,
        "low_penalty": 12,
        "medium_penalty": 5,
    },
}

REAL_JOURNALS = load_yaml_config(ROOT / "config" / "journals.yaml")
REAL_KEYWORDS = load_yaml_config(ROOT / "config" / "keywords.yaml")
REAL_SCORING = load_yaml_config(ROOT / "config" / "scoring.yaml")
REAL_CATEGORIES = load_yaml_config(ROOT / "config" / "categories.yaml")
REAL_ELITE_JOURNALS = load_yaml_config(ROOT / "config" / "elite_journals.yaml")


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

    def test_low_result_specificity_is_downgraded_to_optional_reading(self):
        paper = {
            "title": "Factors associated with return-to-sport outcomes following pathogen-confirmed acute respiratory infections in athletes: AWARE X study",
            "abstract": (
                "OBJECTIVE: To identify factors associated with return-to-sport outcomes after acute respiratory infections in athletes. "
                "METHODS: This prospective observational cohort examined athlete follow-up. "
                "CONCLUSIONS: Follow-up may support return-to-sport decisions."
            ),
            "journal": "British Journal of Sports Medicine",
            "doi": "10.1000/awarex",
            "article_types": ["Journal Article"],
        }
        scored = score_paper(paper, JOURNALS, KEYWORDS, SCORING)

        self.assertLess(scored["result_specificity_score"], 50)
        self.assertLess(scored["score_breakdown"]["result_specificity_penalty"], 0)
        self.assertEqual(scored["reading_priority"], "可选阅读")

    def test_low_information_article_cannot_receive_five_stars(self):
        paper = {
            "title": "Exercise physiology and training outcomes in adults",
            "abstract": "BACKGROUND: This article discusses exercise physiology. CONCLUSIONS: Further research is needed.",
            "journal": "British Journal of Sports Medicine",
            "article_types": ["Journal Article"],
        }
        scored = score_paper(
            paper,
            REAL_JOURNALS,
            REAL_KEYWORDS,
            REAL_SCORING,
            categories_config=REAL_CATEGORIES,
            elite_journals_config=REAL_ELITE_JOURNALS,
        )

        self.assertLess(scored["result_specificity_score"], 50)
        self.assertLessEqual(scored["score"], 69)
        self.assertEqual(scored["reading_priority"], "可选阅读")

    def test_weakly_related_ptsd_nature_communications_article_is_demoted(self):
        paper = {
            "title": "Integrated proteomic and metabolomic analyses implicate redox-metabolic pathways in PTSD-associated multisystem disease and accelerated aging.",
            "abstract": "Proteomic and metabolomic profiles were analyzed in PTSD-associated multisystem disease and accelerated aging.",
            "journal": "Nature Communications",
            "article_types": ["Journal Article"],
        }
        scored = score_paper(
            paper,
            REAL_JOURNALS,
            REAL_KEYWORDS,
            REAL_SCORING,
            categories_config=REAL_CATEGORIES,
            elite_journals_config=REAL_ELITE_JOURNALS,
        )

        self.assertFalse(scored["classification"]["is_elite_radar"])
        self.assertLess(scored["score"], 70)
        self.assertLessEqual(scored["score_breakdown"]["score_cap"], 0)


if __name__ == "__main__":
    unittest.main()
