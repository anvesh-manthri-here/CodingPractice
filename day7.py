# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Two-Sum
# From: daily@techseries.dev  |  Sent: 2019-09-03  |  Asked by: Facebook
#
# You are given a list of numbers, and a target number k. Return whether or not there are two numbers in the list that add up to k.
#
# Example:
# Given [4, 7, 1, -3, 2] and k = 5,
# return true since 4 + 1 = 5.
#
# def two_sum(list, k):
#   # Fill this in.
#
# Try to do it in a single pass of the list.
#
# Original email: https://mail.google.com/mail/u/0/#all/16cf78e176c04451

# Two-Sum

def two_sum(list, k):
	list = set(list)
	for i in list:
		if k-i in list:
			print("{0} = {1} + {2} ".format(k, i, k-i))
			return True
	return False


print(two_sum([4,7,1,-3,2], 5))
# True
print(two_sum([4,7,1,-3,2], 7))
# True
print(two_sum([4,7,1,-3,2], 4))
# True
