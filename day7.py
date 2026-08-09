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
