# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Queue Using Two Stacks
# From: daily@techseries.dev  |  Sent: 2019-09-30  |  Asked by: Apple
#
# Implement a queue class using two stacks. A queue is a data structure that supports the FIFO protocol (First in = first out). Your class should support the enqueue and dequeue methods like a standard queue.
#
# class Queue:
#   def __init__(self):
#     # Fill this in.
#
#   def enqueue(self, val):
#     # Fill this in.
#
#   def dequeue(self):
#     # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d829675473d614

# Queue Using Two Stacks
# Implement a queue class using two stacks. A queue is a data structure that supports the FIFO protocol (First in = first out). Your class should support the enqueue and dequeue methods like a standard queue.

class Queue:
    def __init__(self):
        self.__isFirstMain = true
        self.__stack1 = []
        self.__stack2 = []
        
    def enqueue(self, val):
        while len(self.__stack1):
            self.__stack2.append(self.__stack1.pop())
        self.__stack1.append(val)
        while len(self.__stack2):
            self.__stack1.append(self.__stack2.pop())

    def dequeue(self):
        return self.__stack1.pop()

q = Queue()
q.enqueue(1)
q.enqueue(2)
q.enqueue(3)
print q.dequeue()
print q.dequeue()
print q.dequeue()
# 1 2 3
