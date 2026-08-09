# Longest common substring
# https://www.techiedelight.com/longest-common-substring-problem/

def LCS_basic(x, y, m, n):
	table = [[0]*(m+1) for i in range(n+1)]
	
	max = 0
	for j in range(1, n+1):
		for i in range(1, m+1):
			if x[i-1] is y[j-1]:
				table[j][i] = table[j-1][i-1] + 1
				if table[j][i] > max:
					max = table[j][i]
	return max



X = 'ABABC'
Y = 'BABCA'

print("Basic : "+ str(LCS_basic(X,Y,len(X),len(Y))))
