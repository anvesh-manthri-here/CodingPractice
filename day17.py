# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Find Cycles in a Graph
# From: daily@techseries.dev  |  Sent: 2019-09-14  |  Asked by: Facebook
#
# Given an undirected graph, determine if a cycle exists in the graph.
#
# def find_cycle(graph):
#   # Fill this in.
#
# graph = {
#   'a': {'a2':{}, 'a3':{} },
#   'b': {'b2':{}},
#   'c': {}
# }
# print find_cycle(graph)
# # False
# graph['c'] = graph
# print find_cycle(graph)
# # True
#
# Can you solve this in linear time, linear space?
#
# Original email: https://mail.google.com/mail/u/0/#all/16d3031f33b4282e

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
