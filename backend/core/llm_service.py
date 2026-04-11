from pydantic import BaseModel

class LLMResponseBase(BaseModel):
    text: str
    fallback_used: bool = False

class LLMService:
    def __init__(self):
        pass

    async def generate(self, prompt: str, fallback: str) -> LLMResponseBase:
        # Mock LLM behavior
        return LLMResponseBase(text="This is a mocked LLM response.", fallback_used=True)
