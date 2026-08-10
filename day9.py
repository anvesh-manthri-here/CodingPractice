# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Non-decreasing Array with Single Modification
# From: daily@techseries.dev  |  Sent: 2019-09-05  |  Asked by: Microsoft
#
# You are given an array of integers in an arbitrary order. Return whether or not it is possible to make the array non-decreasing by modifying at most 1 element to any value.
#
# We define an array is non-decreasing if array[i] <= array[i + 1] holds for every i (1 <= i < n).
#
# Example:
# [13, 4, 7] should return true, since we can modify 13 to any value 4 or less, to make it non-decreasing.
# [13, 4, 1] however, should return false, since there is no way to modify just one element to make the array non-decreasing.
#
# def check(lst):
#   # Fill this in.
#
# Can you find a solution in O(n) time?
#
# Original email: https://mail.google.com/mail/u/0/#all/16d01daa4cd42c0d

# Non-decreasing Array with Single Modification
# Can you find a solution in O(n) time?

def check(lst):
	if len(lst)<2:
		return True

	one_done = False
	for i in range(1, len(lst)):
		if lst[i-1] > lst[i]:
			if one_done:
				return False
			else:
				one_done = True
	else:
		return True



print(check([13, 4, 7]))
# True
print(check([5,1,3,2,5]))
# False