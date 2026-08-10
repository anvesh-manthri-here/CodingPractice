# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Find Pythagorean Triplets
# From: daily@techseries.dev  |  Sent: 2019-09-10  |  Asked by: Uber
#
# Given a list of numbers, find if there exists a pythagorean triplet in that list. A pythagorean triplet is 3 variables a, b, c where a^2 + b^2 = c^2
#
# Example:
# Input: [3, 5, 12, 5, 13]
# Output: True
#
# Here, 5^2 + 12^2 = 13^2.
#
# def findPythagoreanTriplets(nums):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d1b99315289108

# Find Pythagorean Triplets

def findPythagoreanTriplets(nums):
	nmaps = {}
	for i in nums:
		i = i*i
		if i in nmaps:
			nmaps[i]+=1
		else:
			nmaps[i] = 1
	
	for k1,v1 in nmaps.items():
		if v1 > 1:
			if k1<<1 in nmaps:
				return True
		for k2, v2 in nmaps.items():
			if k1+k2 in nmaps:
				return True
	return False

print(findPythagoreanTriplets([3, 12, 5, 13]))
# True