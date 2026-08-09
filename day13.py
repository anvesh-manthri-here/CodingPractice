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