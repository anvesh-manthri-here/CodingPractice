# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Reverse a Linked List
# From: daily@techseries.dev  |  Sent: 2019-09-01  |  Asked by: Google
#
# Given a singly-linked list, reverse the list. This can be done iteratively or recursively. Can you get both solutions?
#
# Example:
# Input: 4 -> 3 -> 2 -> 1 -> 0 -> NULL
# Output: 0 -> 1 -> 2 -> 3 -> 4 -> NULL
#
# class ListNode(object):
#   def __init__(self, x):
#     self.val = x
#     self.next = None
#
#   # Iterative Solution
#   def reverseIteratively(self, head):
#     # Implement this.
#
#   # Recursive Solution
#   def reverseRecursively(self, head):
#     # Implement this.
#
# Original email: https://mail.google.com/mail/u/0/#all/16ced40cd5923c9b

# Reverse a Linked List

class ListNode(object):
	def __init__(self, x):
		self.val = x
		self.next = None

	# Function to print the list
	def printList(self):
		node = self
		output = '' 
		while node != None:
			output += str(node.val)
			output += " "
			node = node.next
		print(output)

	# Iterative Solution
	def reverseIteratively(self, head):
		rhead = None

		while head:
			temp = head
			head = head.next
			temp.next = rhead
			rhead = temp
		return rhead


	# Recursive Solution      
	def reverseRecursively(self, head):
		if not head.next:
			return head
		self.reverseRecursively(head.next)
		temp = head.next
		head.next = None
		temp.next = head
		return temp

# Test Program
# Initialize the test list: 
testHead = ListNode(4)
node1 = ListNode(3)
testHead.next = node1
node2 = ListNode(2)
node1.next = node2
node3 = ListNode(1)
node2.next = node3
testTail = ListNode(0)
node3.next = testTail

print("Initial list: ")
testHead.printList()
# 4 3 2 1 0
#testHead.reverseIteratively(testHead)
testHead.reverseRecursively(testHead)
print("List after reversal: ")
testTail.printList()
# 0 1 2 3 4