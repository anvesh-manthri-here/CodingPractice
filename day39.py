# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Deepest Node in a Binary Tree
# From: daily@techseries.dev  |  Sent: 2019-10-06  |  Asked by: Google
#
# You are given the root of a binary tree. Return the deepest node (the furthest node from the root).
#
# Example:
#     a
#    / \
#   b   c
#  /
# d
#
# The deepest node in this tree is d at depth 3.
#
# class Node(object):
#   def __init__(self, val):
#     self.val = val
#     self.left = None
#     self.right = None
#
# def deepest(node):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16da19e252d331e1

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
