from agents.evaluator_pipeline import EvaluatorPipeline


class LangChainEvaluator(EvaluatorPipeline):
    """Evaluation runner using LangChain structured output for semantic operator note audits."""

    def __init__(self):
        super().__init__(backend="langchain")
