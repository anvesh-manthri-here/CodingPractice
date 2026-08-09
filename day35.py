# Merge K Sorted Linked Lists
# You are given an array of k sorted singly linked lists. Merge the linked lists into a single sorted linked list and return it.


class Node(object):
    def __init__(self, val, next=None):
        self.val = val
        self.next = next
        
    def __str__(self):
        c = self
        answer = ""
        while c:
            answer += str(c.val) if c.val else ""
            answer += ','
            c = c.next
        return answer[:-1]

def merge_two_lists(lst1, lst2):
    backup = Node(None)
    final = backup
    while lst1 and lst2:
        if lst1.val <= lst2.val:
            final.next = lst1
            lst1 = lst1.next
        else:
            final.next = lst2
            lst2 = lst2.next
        final = final.next
        final.next = None

    if lst1:
        final.next = lst1
    if lst2:
        final.next = lst2
    return backup.next

def merge(lists):
    while len(lists) > 1:
        front = 0
        end = len(lists) - 1
        while front < end:
            lists[front] = merge_two_lists(lists[front], lists[end])
            del(lists[end])
            front += 1
            end -= 1
    return lists[0]


a = Node(1, Node(3, Node(15)))
b = Node(2, Node(4, Node(6)))
c = Node(3, Node(4, Node(10, Node(12))))
d = Node(9, Node(14, Node(20, Node(27))))
print merge([a, b, c, d])
# 1,2,3,3,4,4,6,9,10,12,14,15,20,27





