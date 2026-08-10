# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Floor and Ceiling of a Binary Search Tree
# From: daily@techseries.dev  |  Sent: 2019-09-06  |  Asked by: Apple
#
# Given an integer k and a binary search tree, find the floor (less than or equal to) of k, and the ceiling (larger than or equal to) of k. If either does not exist, then print them as None.
#
# class Node:
#   def __init__(self, value):
#     self.left = None
#     self.right = None
#     self.value = value
#
# def findCeilingFloor(root_node, k, floor=None, ceil=None):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d07007e7c0f1d2

# Floor and Ceiling of a Binary Search Tree

class Node:
	def __init__(self, value):
		self.left = None
		self.right = None
		self.value = value

def findCeilingFloor(root_node, k, floor=None, ceil=None):
	if root_node is None:
		return (floor,ceil)
	
	if root_node.value is k:
		return (k,k)

	if root_node.value<k:
		floor = root_node.value
		return findCeilingFloor(root_node.right, k, floor, ceil)
	else:
		ceil = root_node.value
		return findCeilingFloor(root_node.left, k, floor, ceil)



root = Node(8) 
root.left = Node(4) 
root.right = Node(12) 
  
root.left.left = Node(2) 
root.left.right = Node(6) 
  
root.right.left = Node(10) 
root.right.right = Node(14) 

test = [1,4,5,7,9]
for t in test:
	print("k : {0}, ans : {1}".format(t,str(findCeilingFloor(root, t))))

# (None, 2)
# (4, 4)
# (4, 6)
# (6, 8)
# (8, 10)
