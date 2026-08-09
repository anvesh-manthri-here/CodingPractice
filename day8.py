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
