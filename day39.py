# Deepest Node in a Binary Tree
# You are given the root of a binary tree. Return the deepest node (the furthest node from the root).

class Node(object):
    def __init__(self, val):
        self.val = val
        self.left = None
        self.right = None
        
    def __repr__(self):
        # string representation
        return self.val


def deepest(node):
    if not node:
        return None, 0

    if not node.left and not node.right:
        return node.val, 1

    left = deepest(node.left)
    right = deepest(node.right)
    if right is None or left[1] >= right[1]:
        return left[0], left[1]+1
    else:
        return right[0], right[1]+1




root = Node('a')
root.left = Node('b')
root.left.left = Node('d')
root.right = Node('c')

print deepest(root)
# (d, 3)
