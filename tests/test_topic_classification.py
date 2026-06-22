import unittest

from src.classify_papers import classify_paper
from src.utils import ROOT, load_yaml_config


CATEGORIES = load_yaml_config(ROOT / "config" / "categories.yaml")
ELITE_JOURNALS = load_yaml_config(ROOT / "config" / "elite_journals.yaml")
KEYWORDS = load_yaml_config(ROOT / "config" / "keywords.yaml")


class TopicClassificationTests(unittest.TestCase):
    def classify(self, title, abstract="", journal="Sports Medicine"):
        return classify_paper(
            {
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "article_types": ["Journal Article"],
            },
            categories_config=CATEGORIES,
            elite_journals_config=ELITE_JOURNALS,
            keywords_config=KEYWORDS,
        )

    def test_uk_biobank_physical_activity_is_population_database(self):
        result = self.classify(
            "UK Biobank device-measured physical activity and mortality",
            "Accelerometer-derived physical activity was studied in a prospective cohort.",
        )

        self.assertIn("体力活动与公开数据库", result["directions"])
        self.assertIn("公开数据库", result["study_type_tags"])
        self.assertIn("UK Biobank", result["data_sources"])

    def test_obesity_phenotype_is_obesity_heterogeneity(self):
        result = self.classify(
            "Obesity phenotype and insulin resistance",
            "This cohort used latent class analysis to identify obesity subtypes.",
        )

        self.assertIn("肥胖异质性", result["directions"])

    def test_skeletal_muscle_dna_methylation_is_muscle_omics(self):
        result = self.classify(
            "Skeletal muscle DNA methylation after resistance training",
            "RNA-seq and DNA methylation were profiled in skeletal muscle.",
        )

        self.assertIn("肌肉表观遗传/多组学", result["directions"])
        self.assertIn("多组学", result["study_type_tags"])

    def test_nature_metabolism_exercise_obesity_is_elite_radar(self):
        result = self.classify(
            "Exercise remodels adipose tissue metabolism in obesity",
            "Skeletal muscle and obesity metabolism were analyzed after exercise.",
            journal="Nature Metabolism",
        )

        self.assertIn("顶刊雷达", result["directions"])
        self.assertTrue(result["is_elite_radar"])
        self.assertGreaterEqual(result["personal_relevance_score"], 60)

    def test_dietary_fat_weight_loss_is_lipid_weight_loss(self):
        result = self.classify(
            "Dietary fat and weight loss in adults with obesity",
            "Fatty acid intake and lipid metabolism were measured.",
        )

        self.assertIn("脂肪与减肥", result["directions"])

    def test_protein_supplementation_resistance_training_is_sports_nutrition(self):
        result = self.classify(
            "Protein supplementation and resistance training for hypertrophy",
            "Whey protein, leucine and muscle protein synthesis were assessed.",
        )

        self.assertIn("运动营养", result["directions"])

    def test_aware_x_return_to_sport_infection_is_not_animal_model(self):
        result = self.classify(
            "Factors associated with return-to-sport outcomes following pathogen-confirmed acute respiratory infections in athletes: AWARE X study",
            "This prospective observational athlete cohort examined factors associated with return-to-sport after acute respiratory infections.",
            journal="British Journal of Sports Medicine",
        )

        self.assertIn("运动医学", result["directions"])
        self.assertIn("运动员健康", result["directions"])
        self.assertIn("呼吸道感染", result["directions"])
        self.assertIn("重返运动", result["directions"])
        self.assertIn("人群队列", result["study_type_tags"])
        self.assertIn("观察性研究", result["study_type_tags"])
        self.assertNotIn("动物实验", result["study_type_tags"])
        self.assertNotIn("动物实验", result["data_sources"])


if __name__ == "__main__":
    unittest.main()
