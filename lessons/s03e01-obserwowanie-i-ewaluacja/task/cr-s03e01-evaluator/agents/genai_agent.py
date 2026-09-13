from agents.evaluator_pipeline import EvaluatorPipeline


class GenAIEvaluator(EvaluatorPipeline):
    """Evaluation runner using Google GenAI SDK for semantic operator note audits."""

    def __init__(self):
        super().__init__(backend="genai")
