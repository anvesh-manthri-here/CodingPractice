# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Find the non-duplicate number
# From: daily@techseries.dev  |  Sent: 2019-09-04  |  Asked by: Facebook
#
# Given a list of numbers, where every number shows up twice except for one number, find that one number.
#
# Example:
# Input: [4, 3, 2, 4, 1, 3, 2]
# Output: 1
#
# def singleNumber(nums):
#   # Fill this in.
#
# Challenge: Find a way to do this using O(1) memory.
#
# Original email: https://mail.google.com/mail/u/0/#all/16cfcb374ae92204

# Find the non-duplicate number
# Challenge: Find a way to do this using O(1) memory.


def singleNumber(nums):
	res = 0
	for i in nums:
		res ^= i
	return res

print(singleNumber([4, 3, 2, 4, 1, 3, 2]))
# 1
print(singleNumber([4, 3, 2, 4, 1, 2, 1]))
# 3
