# Number of Ways to Climb Stairs

ans_dict = {}

def staircase(n):
	if n is 1 or n is 2:
		return n
	if n in ans_dict:
		return ans_dict[n]
	ans = staircase(n-1) + staircase(n-2)
	ans_dict[n] = ans
	return ans

print(staircase(4))
# 5
print(staircase(5))
# 8
print(staircase(6))
