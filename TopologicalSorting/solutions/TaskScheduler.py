"""
Design a General-Purpose Task Scheduler (own exercise, no LeetCode link)
Pattern: DFS topo sort + parent-pointer tracking to report the actual cycle

PROBLEM (self-designed, common "explain the cycle" interview follow-up)
--------------------------------------------------------------------------
Given a dict `tasks: {task_name: [dependency_names...]}`, where each
dependency must run BEFORE the task itself, return a valid execution order
(dependencies first). If a circular dependency exists, don't just say
"cycle detected" — raise a ValueError naming the ACTUAL cycle path, e.g.
"Circular dependency involving: A -> B -> C -> A".

This is the natural follow-up interviewers ask after any topo sort problem:
"Great, now instead of returning [] on failure, tell me exactly which tasks
are stuck in a cycle." It forces you to track *how you got to* the node
that closes the cycle, not just *that* a cycle exists.

WHY DFS (NOT KAHN'S) IS THE RIGHT TOOL HERE
-----------------------------------------------
Kahn's BFS can tell you a cycle exists (leftover nodes with indegree > 0 at
the end), but reconstructing the exact cycle from Kahn's leftover indegree
map is awkward — it tells you WHICH nodes are stuck, not in what order they
depend on each other.

DFS-based topo sort naturally tracks the current recursion PATH (the chain
of "how did I get here" calls). If, while exploring, we hit a node that is
already GRAY (currently being explored, i.e. it's an ancestor on the
current path — not just previously visited), we've found a back-edge, and
the cycle is exactly the suffix of the path from that ancestor to here.

Standard 3-color DFS:
  WHITE = unvisited
  GRAY  = currently on the recursion stack (being explored)
  BLACK = fully finished (all its dependencies resolved)

- A WHITE -> GRAY neighbor found during DFS = tree edge, recurse into it.
- A GRAY neighbor found = BACK EDGE = cycle! Reconstruct it from `path`.
- A BLACK neighbor found = already fully resolved elsewhere, safe to skip
  (this is what makes the algorithm O(V + E) instead of exponential).

Post-order append (append to `order` AFTER exploring all dependencies) is
what makes this a valid topological order: a task is only recorded once
everything IT depends on has already been recorded.

APPROACH
--------
- state: dict task -> WHITE/GRAY/BLACK, default WHITE.
- path: list acting as the current DFS call stack (for cycle reconstruction
  and also usable to print a friendly error).
- dfs(node):
    mark node GRAY, push onto path
    for each dependency dep of node:
        if dep unknown, treat it as a dependency-free leaf (auto-register)
        if state[dep] == GRAY: cycle! path[path.index(dep):] + [dep] is the
            cycle loop.
        if state[dep] == WHITE: recurse
        (if BLACK: already resolved, skip)
    pop node off path, mark BLACK, append to result order
- Run dfs from every WHITE node (handles disconnected components).

Time:  O(V + E) — each node visited once, each edge examined once.
Space: O(V + E) for state/path/order plus the recursion stack (O(V) worst
       case for a long chain).

TEST CASES
----------
1) {"deploy": ["test"], "test": ["build"], "build": []}
   -> valid order: build, test, deploy

2) {"A": ["B", "C"], "B": [], "C": ["B"]}
   -> valid order where B comes before both A and C, and C before A
      (e.g. B, C, A)

3) {"A": ["B"], "B": ["C"], "C": ["A"]}
   -> raises ValueError("Circular dependency involving: A -> B -> C -> A")

4) {"X": [], "Y": []}   (no dependencies at all, disconnected)
   -> valid order containing both X and Y in either order
"""

from typing import Dict, List


def schedule_tasks(tasks: Dict[str, List[str]]) -> List[str]:
    """Return a valid dependency-respecting execution order for `tasks`.

    `tasks` maps each task name to the list of task names that must run
    BEFORE it. Dependencies mentioned but not present as a top-level key
    are treated as dependency-free leaves and auto-registered.

    Raises ValueError naming the exact cycle if one exists, e.g.:
        "Circular dependency involving: A -> B -> C -> A"
    """
    tasks = dict(tasks)  # shallow copy; we may auto-register missing deps

    WHITE, GRAY, BLACK = 0, 1, 2
    state = {task: WHITE for task in tasks}
    order: List[str] = []

    def dfs(node: str, path: List[str]) -> None:
        state[node] = GRAY
        path.append(node)

        for dep in tasks.get(node, []):
            if dep not in tasks:
                tasks[dep] = []
                state[dep] = WHITE

            if state[dep] == GRAY:
                cycle_start = path.index(dep)
                cycle = path[cycle_start:] + [dep]
                raise ValueError(
                    "Circular dependency involving: " + " -> ".join(cycle)
                )
            if state[dep] == WHITE:
                dfs(dep, path)
            # state[dep] == BLACK -> already fully resolved, nothing to do

        path.pop()
        state[node] = BLACK
        order.append(node)

    for task in list(tasks.keys()):
        if state[task] == WHITE:
            dfs(task, [])

    return order


def _respects_dependencies(tasks: Dict[str, List[str]], order: List[str]) -> bool:
    position = {task: i for i, task in enumerate(order)}
    for task, deps in tasks.items():
        for dep in deps:
            if position[dep] > position[task]:
                return False
    return True


if __name__ == "__main__":
    # Case 1: simple chain
    tasks1 = {"deploy": ["test"], "test": ["build"], "build": []}
    order1 = schedule_tasks(tasks1)
    assert order1 == ["build", "test", "deploy"]

    # Case 2: diamond-shaped dependencies
    tasks2 = {"A": ["B", "C"], "B": [], "C": ["B"]}
    order2 = schedule_tasks(tasks2)
    assert _respects_dependencies(tasks2, order2)
    assert order2.index("B") < order2.index("C") < order2.index("A")

    # Case 3: cycle -> must raise with the exact cycle path
    tasks3 = {"A": ["B"], "B": ["C"], "C": ["A"]}
    try:
        schedule_tasks(tasks3)
        assert False, "expected ValueError for circular dependency"
    except ValueError as e:
        assert "A -> B -> C -> A" in str(e), f"unexpected message: {e}"

    # Case 4: disconnected components, no dependencies
    tasks4 = {"X": [], "Y": []}
    order4 = schedule_tasks(tasks4)
    assert sorted(order4) == ["X", "Y"]

    print("All Task Scheduler tests passed!")
