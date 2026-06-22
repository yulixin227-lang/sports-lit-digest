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

    def test_model_word_alone_is_not_animal_model(self):
        result = self.classify(
            "Prediction model for return-to-sport outcomes in athletes",
            "This human observational cohort developed a statistical model in athletes.",
        )

        self.assertNotIn("动物实验", result["study_type_tags"])
        self.assertNotIn("动物实验", result["data_sources"])

    def test_caffeine_swimming_meta_analysis_is_not_animal_model(self):
        result = self.classify(
            "Caffeine makes a splash: a systematic review and multilevel meta-analysis exploring the effects of caffeine intake on swimming performance.",
            "This systematic review and meta-analysis examined caffeine intake and swimming performance in human sport settings.",
            journal="Journal of the International Society of Sports Nutrition",
        )

        self.assertIn("运动营养", result["directions"])
        self.assertIn("运动表现", result["directions"])
        self.assertIn("系统综述", result["study_type_tags"])
        self.assertIn("Meta分析", result["study_type_tags"])
        self.assertNotIn("动物实验", result["study_type_tags"])
        self.assertNotIn("动物实验", result["data_sources"])

    def test_emg_rotator_cuff_human_fatigue_is_not_animal_model(self):
        result = self.classify(
            "Electromyography of rotator cuff and deltoid fatigue during shoulder exercise",
            "Surface electromyography was recorded in human participants to assess rotator cuff and deltoid fatigue.",
            journal="Journal of Electromyography and Kinesiology",
        )

        self.assertIn("肌电图", result["directions"])
        self.assertIn("神经肌肉控制", result["directions"])
        self.assertIn("疲劳", result["directions"])
        self.assertIn("肩部肌群", result["directions"])
        self.assertIn("人体研究", result["directions"])
        self.assertNotIn("动物实验", result["study_type_tags"])

    def test_uk_biobank_cohort_is_not_animal_model(self):
        result = self.classify(
            "UK Biobank cohort study of physical activity and cardiometabolic outcomes",
            "A prospective cohort used accelerometer-measured physical activity in UK Biobank participants.",
        )

        self.assertIn("体力活动与公开数据库", result["directions"])
        self.assertIn("公开数据库", result["study_type_tags"])
        self.assertNotIn("动物实验", result["study_type_tags"])

    def test_explicit_mice_signal_is_animal_model(self):
        result = self.classify(
            "High-fat diet-induced mice show skeletal muscle mitochondrial adaptations after exercise",
            "Mice were exposed to a high-fat diet-induced obesity mouse model and exercise training.",
        )

        self.assertIn("动物实验", result["study_type_tags"])
        self.assertIn("动物实验", result["data_sources"])

    def test_ptsd_nature_omics_is_not_sports_nutrition_or_elite_radar(self):
        result = self.classify(
            "Integrated proteomic and metabolomic analyses implicate redox-metabolic pathways in PTSD-associated multisystem disease and accelerated aging.",
            "Proteomic and metabolomic profiles were analyzed in PTSD-associated multisystem disease and accelerated aging.",
            journal="Nature Communications",
        )

        self.assertFalse(result["is_elite_radar"])
        self.assertNotIn("运动营养", result["directions"])
        self.assertNotIn("肌肉表观遗传/多组学", result["directions"])
        self.assertNotIn("动物实验", result["study_type_tags"])
        self.assertTrue(result["demote_reason"])

    def test_masld_tyg_uk_biobank_is_not_dietary_fat(self):
        result = self.classify(
            "C-reactive protein-triglyceride-glucose index and cardiometabolic multimorbidity in MASLD: a UK Biobank cohort study",
            "This UK Biobank cohort examined CRP-triglyceride-glucose index and cardiometabolic risk in MASLD.",
        )

        self.assertIn("公开数据库", result["directions"])
        self.assertIn("心代谢风险", result["directions"])
        self.assertIn("MASLD", result["directions"])
        self.assertIn("队列研究", result["directions"])
        self.assertNotIn("脂肪与减肥", result["directions"])

    def test_irisin_training_obesity_meta_not_nutrition_or_dietary_fat(self):
        result = self.classify(
            "Effects of different training modalities on circulating irisin levels in overweight and obesity: a systematic review and meta-analysis",
            "Training modalities were compared for circulating irisin in people with overweight and obesity.",
        )

        self.assertIn("运动干预", result["directions"])
        self.assertIn("肥胖", result["directions"])
        self.assertIn("肌因子", result["directions"])
        self.assertNotIn("运动营养", result["directions"])
        self.assertNotIn("脂肪与减肥", result["directions"])

    def test_glp1_oa_scoping_review_is_not_population_database(self):
        result = self.classify(
            "GLP-1 receptor agonists and weight-loss strategies for individuals with obesity and hip or knee osteoarthritis: a scoping review.",
            "This scoping review examined weight-loss strategies including nutritional, physical activity, surgical or pharmacological interventions for adults with obesity and osteoarthritis.",
            journal="British Journal of Sports Medicine",
        )

        self.assertIn("肥胖", result["directions"])
        self.assertIn("骨关节炎", result["directions"])
        self.assertIn("减重策略", result["directions"])
        self.assertIn("肌骨康复", result["directions"])
        self.assertIn("范围综述", result["study_type_tags"])
        self.assertNotIn("体力活动与公开数据库", result["directions"])
        self.assertNotIn("人群队列", result["study_type_tags"])


if __name__ == "__main__":
    unittest.main()
