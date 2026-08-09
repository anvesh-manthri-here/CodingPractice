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