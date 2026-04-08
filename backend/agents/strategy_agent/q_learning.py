class QLearningAgent:
    def __init__(self):
        # Tabular Q
        self.q_table = {}
        
    def update(self, state: str, action: str, reward: float, next_state: str):
        # Q(s, a) = Q(s, a) + alpha * [r + gamma * max_a(Q(s', a)) - Q(s, a)]
        pass
        
    def policy(self, state: str) -> str:
        # Epsilon-greedy
        return "hint"

q_learning_agent = QLearningAgent()
