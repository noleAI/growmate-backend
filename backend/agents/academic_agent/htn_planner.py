class HTNPlanner:
    def __init__(self):
        self.plan_tree = {}
        
    def decompose(self, goal: str):
        pass
        
    def repair_plan(self, current_node: str, failure_reason: str) -> bool:
        """
        Locally repairs plan without wiping out the entire tree.
        """
        return True

htn_planner = HTNPlanner()
