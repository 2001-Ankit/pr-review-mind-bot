import os
from openai import OpenAI
from dotenv import load_dotenv
from app.llm.base import LLMProvider


load_dotenv(override=True)
class OpenAIProvider(LLMProvider):

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("No open ai api key")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate(self, system_prompt: str, user_prompt: str) -> str:

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content