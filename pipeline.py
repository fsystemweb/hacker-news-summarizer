from haystack import Pipeline
from haystack.components.builders import PromptBuilder
from haystack.components.generators.openai import OpenAIGenerator
from haystack.utils import Secret
from components.hn_fetcher import HackerNewsNewestFetcher
import os
from pathlib import Path
from haystack.core.component import component
from haystack.dataclasses import Document
from typing import List
from dotenv import load_dotenv

@component
class DocumentLoopProcessor:
    """Process each document individually through the LLM."""
    def __init__(self, api_key: str, model_name: str, temperature: float, verbose: bool = False):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.verbose = verbose
    
    @component.output_types(results=List[dict])
    def run(self, documents: List[Document]):
        """Process each document and return results with documents and summaries."""
        from haystack.components.builders import PromptBuilder
        from haystack.components.generators.openai import OpenAIGenerator
        
        template_path = Path(__file__).parent / "prompts" / "hn_summary.j2"
        with open(template_path, "r") as f:
            template = f.read()
        
        results = []
        for doc in documents:
            try:
                # Create prompt for single document
                prompt_builder = PromptBuilder(template=template, required_variables=["doc"])
                prompt = prompt_builder.run(doc=doc)["prompt"]
                
                # Generate summary using LLM
                llm = OpenAIGenerator(
                    model=self.model_name,
                    api_key=Secret.from_token(self.api_key),
                    generation_kwargs={"temperature": self.temperature},
                )
                response = llm.run(prompt=prompt)
                summary = response["replies"][0] if response.get("replies") else "Unable to generate summary"
                
                results.append({
                    "document": doc,
                    "summary": summary
                })
            except Exception as e:
                if self.verbose:
                    print(f"DEBUG: Error processing document '{doc.meta.get('title', 'N/A')}': {e}")
                results.append({
                    "document": doc,
                    "summary": "Error generating summary"
                })
        
        return {"results": results}

def create_hn_summarizer_pipeline(api_key: str, model_name: str, temperature: float, verbose: bool = False) -> Pipeline:
    """
    Creates and returns a Haystack Pipeline for Hacker News summarization.

    :param api_key: OpenAI API key.
    :param model_name: The OpenAI model to use for generation.
    :param temperature: The temperature for the OpenAI model.
    :param verbose: If True, enable verbose logging for components.
    :return: A Haystack Pipeline instance.
    """
    pipeline = Pipeline()

    # Add HackerNewsNewestFetcher component
    pipeline.add_component(
        "hn_fetcher", HackerNewsNewestFetcher(verbose=verbose)
    )

    # Add DocumentLoopProcessor component
    pipeline.add_component(
        "document_processor",
        DocumentLoopProcessor(api_key=api_key, model_name=model_name, temperature=temperature, verbose=verbose)
    )

    # Connect the components
    pipeline.connect("hn_fetcher.documents", "document_processor.documents")

    return pipeline

if __name__ == "__main__":
    # This block is for demonstrating the pipeline structure or drawing it.
    # It won't be executed during normal CLI operation.
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not found. Please set it in your .env file.")
    else:
        print("Creating a dummy pipeline for demonstration...")
        pipeline = create_hn_summarizer_pipeline(api_key=api_key, model_name="gpt-5-mini", temperature=0.5, verbose=True)
        # You can draw the pipeline for visualization:
        # pipeline.draw("hn_summarizer_pipeline.png")
        # print("Pipeline drawn to hn_summarizer_pipeline.png")
