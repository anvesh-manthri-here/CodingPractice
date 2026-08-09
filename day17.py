# Find Cycles in a Graph
# Given an undirected graph, determine if a cycle exists in the graph.

def find_cycle(graph):
    node_stack = []
    node_set = set([])
    for node in graph:
        node_stack.append(node)
        node_set.add(node)

    while len(node_stack) > 0:
        node = node_stack.pop()
        for inner_node in node:
            node_stack.append(inner_node)
            if inner_node in node_set:
                return False
            node_set.add(inner_node)
    return True



graph = {'a': {'a2':{}, 'a3':{} },
         'b': {'b2':{}},
         'c': {}}

print find_cycle(graph)
# False
graph['c'] = graph
print find_cycle(graph)
# True
