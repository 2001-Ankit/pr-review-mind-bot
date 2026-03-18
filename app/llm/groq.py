import os
from openai import OpenAI
from dotenv import load_dotenv
from app.llm.base import LLMProvider


load_dotenv(override=True)
class GroqProvider(LLMProvider):

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("No open ai api key")
        self.client = OpenAI(
      api_key=os.environ.get("GROQ_API_KEY"),
      base_url="https://api.groq.com/openai/v1",
    )
    def generate(self, system_prompt: str, user_prompt: str) -> str:


      response = self.client.responses.create(
      input=system_prompt+user_prompt,
      model="openai/gpt-oss-20b",
      )
      # print(response.output_text)
      return response.output_text

    