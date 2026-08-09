# Spiral Traversal of Grid
# You are given a 2D array of integers. Print out the clockwise spiral traversal of the matrix.

def matrix_spiral_print(M, row_l, row_r, col_l, col_r):
    
    if row_l >= row_r or col_l >= col_r:
        return ''

    out = ''
    for i in range(col_l, col_r):
        out += str(M[row_l][i]) + ' '

    for i in range(row_l + 1, row_r):
        out += str(M[i][col_r - 1]) + ' '

    if row_l + 1 is not row_r:
        for i in range(col_r - 2, col_l - 1, -1):
            out += str(M[row_r - 1][i]) + ' '

    if col_l + 1 is not col_r:
        for i in range(row_r - 2, row_l, -1 ):
            out += str(M[i][col_l]) + ' '

    out += matrix_spiral_print(M, row_l + 1, row_r - 1, col_l + 1, col_r - 1)
    return out



grid = [[1,  2,  3,  4,  5],
        [6,  7,  8,  9,  10],
        [11, 12, 13, 14, 15],
        [16, 17, 18, 19, 20],
        [21, 22, 23, 24, 25]]


print matrix_spiral_print(grid, 0, len(grid), 0, len(grid[0]))
# 1 2 3 4 5 10 15 20 19 18 17 16 11 6 7 8 9 14 13 12

print

grid = [[1],
        [6],
        [1],
        [1]]

print matrix_spiral_print(grid, 0, len(grid), 0, len(grid[0]))
