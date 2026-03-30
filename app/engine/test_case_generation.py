from pydantic import BaseModel




class TestCase(BaseModel):
  __test__ = False
  test_name: str
  description:str
  

class TestGenerator:
    __test__ = False
    def __init__(self, llm):
        self.llm = llm

    def generate_tests(self, code: str):

        system_prompt = """
You are an expert senior software engineer with a 10+ years of experience and knowing the actual problem of the code and flow of program.

Generate high-quality unit tests for the given function or code.

Rules:
- Cover edge cases
- Cover normal cases
- Cover invalid inputs
- Return only valid test code.
"""

        user_prompt = f"""
Generate  unit tests for this code:

{code}
"""

        response = self.llm.generate(system_prompt, user_prompt)

        return response
