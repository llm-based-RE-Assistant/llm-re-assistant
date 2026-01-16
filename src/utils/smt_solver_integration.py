from z3 import Solver, Int, sat

class SMTSolver:
    def check_constraints(self, constraints):
        solver = Solver()
        variables = {}

        for name in constraints:
            variables[name] = Int(name)

        for constraint in constraints.values():
            solver.add(constraint(variables))

        result = solver.check()

        if result == sat:
            return {"status": "SAT", "message": "Constraints are consistent"}

        return {"status": "UNSAT", "message": "Logical conflict detected"}

