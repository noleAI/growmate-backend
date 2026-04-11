from agents.base import IAgent, AgentInput, AgentOutput

class QLearningAgent(IAgent):
    def __init__(self):
        self.q_table = {
            "state_1": {"action_a": 0.5, "action_b": 0.1},
            "state_2": {"action_a": 0.0, "action_b": 0.9}
        }
    
    @property
    def name(self) -> str:
        return "strategy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        # TODO: Implemented logic
        return AgentOutput(action="strategy_action", payload={"q_table": self.q_table})

    def update_q_value(self, state, action, reward, next_state):
        pass

q_learning = QLearningAgent()
