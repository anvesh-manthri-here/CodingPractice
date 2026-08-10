# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Reconstrunct Binary Tree from Preorder and Inorder Traversals
# From: daily@techseries.dev  |  Sent: 2019-10-13  |  Asked by: Microsoft
#
# You are given the preorder and inorder traversals of a binary tree in the form of arrays. Write a function that reconstructs the tree represented by these traversals.
#
# Example:
# Preorder: [a, b, d, e, c, f, g]
# Inorder: [d, b, e, a, f, c, g]
#
# The tree that should be constructed from these traversals is:
#     a
#    / \
#   b   c
#  / \ / \
# d  e f  g
#
# from collections import deque
#
# class Node(object):
#   def __init__(self, val):
#     self.val = val
#     self.left = None
#     self.right = None
#
# def reconstruct(preorder, inorder):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16dc5aa95cbfe43d

# Reconstrunct Binary Tree from Preorder and Inorder Traversals

#You are given the preorder and inorder traversals of a binary tree in the form of arrays. Write a function that reconstructs the tree represented by these traversals.

#Example:
#Preorder: [a, b, d, e, c, f, g]
#Inorder: [d, b, e, a, f, c, g]

#The tree that should be constructed from these traversals is:
#    a
#   / \
#  b   c
# / \ / \
#d  e f  g

from collections import deque
import sys

class Tree(object):
    def __init__(self, preorder, inorder):
        self.preorder = preorder
        self.inorder = inorder
        self.inorder_map = {}
        for i in range(0, len(inorder)):
            self.inorder_map[inorder[i]] = i

    def construct(self, pre_ind, inorder_front, inorder_end):
        if inorder_front >= inorder_end:
            return None

        cur_ind = self.inorder_map[self.preorder[pre_ind]]
        cur_node = Node(self.inorder[cur_ind])
        cur_node.left = self.construct(pre_ind + 1, inorder_front, cur_ind)
        cur_node.right = self.construct(pre_ind + 1 +(cur_ind - inorder_front), cur_ind+1, inorder_end)
        return cur_node

class Node(object):
    def __init__(self, val):
        self.val = val
        self.left = None
        self.right = None
        
    def __str__(self):
        q = deque()
        q.append(self)
        result = ''
        while len(q):
            n = q.popleft()
            result += n.val
            if n.left:
                q.append(n.left)
            if n.right:
                q.append(n.right)
        return result


def reconstruct(preorder, inorder):
    return Tree(preorder, inorder).construct(0, 0, len(inorder))

tree = reconstruct(['a', 'b', 'd', 'e', 'c', 'f', 'g'],
                   ['d', 'b', 'e', 'a', 'f', 'c', 'g'])
print tree
# abcdefg

tree = reconstruct(['A','B','D','E','F','C','G','H','J','L','K'],
                   ['D','B','F','E','A','G','C','L','J','H','K'])
print tree
# ABCDEGHFJKL










