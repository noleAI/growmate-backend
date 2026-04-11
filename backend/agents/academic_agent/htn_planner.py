from agents.base import IAgent, AgentInput, AgentOutput

class HTNPlanner(IAgent):
    @property
    def name(self) -> str:
        return "htn_planner"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        # TODO: Implement HTN logic
        return AgentOutput(action="plan_generated", payload={"tasks": []})

    def repair_plan(self, concept: str, reason: str) -> bool:
        # Mock fixing plan
        return True

htn_planner = HTNPlanner()
