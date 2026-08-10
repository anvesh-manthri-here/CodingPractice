# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Sorting a list with 3 unique numbers
# From: daily@techseries.dev  |  Sent: 2019-09-02  |  Asked by: Google
#
# Given a list of numbers with only 3 unique numbers (1, 2, 3), sort the list in O(n) time.
#
# Example 1:
# Input: [3, 3, 2, 1, 3, 2, 1]
# Output: [1, 1, 2, 2, 3, 3, 3]
#
# def sortNums(nums):
#   # Fill this in.
#
# Challenge: Try sorting the list using constant space.
#
# Original email: https://mail.google.com/mail/u/0/#all/16cf26734e2109d3

# Sorting a list with 3 unique numbers
# Challenge: Try sorting the list using constant space

def sortNums(nums):
	d = {}
	for e in nums:
		try:
			d[e]+=1
		except:
			d[e] = 1
	ans = []
	
	for a in sorted(d.keys()):
		ans.extend([a for i in range(d[a])])
	return ans

print(sortNums([3, 3, 2, 1, 3, 2, 1]))
# [1, 1, 2, 2, 3, 3, 3]