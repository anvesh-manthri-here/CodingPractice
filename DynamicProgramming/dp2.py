# Longest Common Sequence - Find all LCS
# https://www.techiedelight.com/longest-common-subsequence-finding-lcs/


def LCS_basic(x, y, m, n):
	if m is 0 or n is 0:
		return [""]
	if x[m-1] is y[n-1]:
		return [a+x[m-1] for a in LCS_basic(x, y, m-1, n-1)]
	else:
		a = LCS_basic(x, y, m-1, n)
		b = LCS_basic(x, y, m, n-1)
		
		max = -1
		for e in a+b:
			if max<len(e):
				max=len(e)
		
		return [ele for ele in a+b if len(ele) is max]


#X = 'ABCBDAB'
#Y = 'BDCABA'

# X = 'BITING'
# Y = 'SITTING'

X = 'XMJYAUZ'
Y = 'MZJAWXU'

print("basic : " + str(LCS_basic(X,Y,len(X),len(Y))))


