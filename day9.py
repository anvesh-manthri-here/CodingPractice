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