# Longest common subsequence
# https://www.techiedelight.com/longest-common-subsequence/

def LCS_basic(x, y, m, n):
	if m is 0 or n is 0:
		return 0

	if x[m-1] is y[n-1]:
		return LCS_basic(x, y, m-1, n-1) + 1
	else:
		a = LCS_basic(x, y, m-1, n)
		b = LCS_basic(x, y, m, n-1)
		return a if a>b else b

def LCS(x, y, m, n):
	seq = [0]*(m+1)
	for i in range(1,n+1):
		seq[0] = 0
		prev = 0
		for j in range(1,m+1):
			if y[i-1] is x[j-1]:
				cur = seq[j-1] + 1
			else:
				cur = seq[j] if seq[j]>prev else prev
			seq[j-1] = prev
			prev = cur
		seq[m] = prev
	return seq[m]

def get_memorized_table(x, y):
	m = len(x)
	n = len(y)
	
	#initialize table
	table = [[0]*(m+1) for i in range(n+1)]
	
	for i in range(1,n+1):
		for j in range(1, m+1):
			if x[j-1] == y[i-1]:
				table[i][j] = table[i-1][j-1] + 1
			else:
				table[i][j] = table[i-1][j] if table[i-1][j]>table[i][j-1] else table[i][j-1]
				
	# Print out the table
	y_ax = -1
	print("table :\n  0, {0} ".format(", ".join(list(x))))
	for ele in table:
		cha = "0" if y_ax is -1 else y[y_ax]
		print(cha+str(ele))
		y_ax += 1
		
	return table


#X = 'ABCBDAB'
#Y = 'BDCABA'

X = 'BITING'
Y = 'SITTING'

#X = 'XMJYAUZ'
#Y = 'MZJAWXU'


print("basic : " + str(LCS_basic(X,Y,len(X),len(Y))))
print("memorized : " + str(LCS(X,Y,len(X),len(Y))))
get_memorized_table(X,Y)
