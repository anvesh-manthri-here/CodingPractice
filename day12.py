# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Number of Ways to Climb Stairs
# From: daily@techseries.dev  |  Sent: 2019-09-09  |  Asked by: LinkedIn
#
# You are given a positive integer N which represents the number of steps in a staircase. You can either climb 1 or 2 steps at a time. Write a function that returns the number of unique ways to climb the stairs.
#
# def staircase(n):
#   # Fill this in.
#
# print staircase(4)
# # 5
# print staircase(5)
# # 8
#
# Can you find a solution in O(n) time?
#
# Original email: https://mail.google.com/mail/u/0/#all/16d1672c03e8917e

# Number of Ways to Climb Stairs

ans_dict = {}

def staircase(n):
	if n is 1 or n is 2:
		return n
	if n in ans_dict:
		return ans_dict[n]
	ans = staircase(n-1) + staircase(n-2)
	ans_dict[n] = ans
	return ans

print(staircase(4))
# 5
print(staircase(5))
# 8
print(staircase(6))
