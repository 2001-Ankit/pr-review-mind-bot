import os
from dotenv import load_dotenv
from google import genai
from app.llm.base import LLMProvider





class GeminiProvider(LLMProvider):
    load_dotenv(override=True)
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    def generate(self, system_prompt: str, user_prompt: str) -> str:

        full_prompt = f"""
                      {system_prompt}

                      {user_prompt}
                      """

        print("full prompt")
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=full_prompt
        )
        print(response.text)
        return response.text