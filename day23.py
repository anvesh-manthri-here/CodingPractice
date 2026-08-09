# Remove Consecutive Nodes that Sum to 0

# Given a linked list of integers, remove all consecutive nodes that sum up to 0.

class Node:
    def __init__(self, value, next=None):
        self.value = value
        self.next = next

def removeConsecutiveSumTo0(node):
    head = Node(0)
    head.next = node

    sum = 0
    sum_map = {}
    front = head

    while front:
        sum += front.value
        if sum in sum_map:
            sum_map[sum].next = front.next
            sum_map = {0: sum_map[sum]}
            sum = 0
        else:
            sum_map[sum] = front
        front = front.next

    return head.next


node = Node(10)
node.next = Node(5)
node.next.next = Node(-3)
node.next.next.next = Node(-3)
node.next.next.next.next = Node(1)
node.next.next.next.next.next = Node(5)
node.next.next.next.next.next.next = Node(4)
node.next.next.next.next.next.next.next = Node(-4)
node.next.next.next.next.next.next.next.next = Node(-3)
#node = Node(5)
#node.next = Node(-3)
#node.next.next = Node(-3)
#node.next.next.next = Node(1)
#node.next.next.next.next = Node(6)
#node.next.next.next.next.next = Node(4)
#node.next.next.next.next.next.next = Node(-4)
#node.next.next.next.next.next.next.next = Node(-3)
node = removeConsecutiveSumTo0(node)
while node:
    print node.value
    node = node.next
# 10 5 -3
