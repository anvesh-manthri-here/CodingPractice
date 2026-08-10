# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Word Search
# From: daily@techseries.dev  |  Sent: 2019-09-15  |  Asked by: Amazon
#
# You are given a 2D array of characters, and a target string. Return whether or not the word target word exists in the matrix. Unlike a standard word search, the word must be either going left-to-right, or top-to-bottom in the matrix.
#
# Example:
# [['F', 'A', 'C', 'I'],
#  ['O', 'B', 'Q', 'P'],
#  ['A', 'N', 'O', 'B'],
#  ['M', 'A', 'S', 'S']]
#
# Given this matrix, and the target word FOAM, you should return true, as it can be found going up-to-down in the first column.
#
# def word_search(matrix, word):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d355843e77a3dd

# Word Search
# You are given a 2D array of characters, and a target string. Return whether or not the word target word exists in the matrix. Unlike a standard word search, the word must be either going left-to-right, or top-to-bottom in the matrix.

def word_search(matrix, word):
    # pre-possessing matrix
    word_dict = dict()
    row = -1
    for each_row in matrix:
        row += 1
        col = -1
        for symbol in each_row:
            col += 1
            if symbol not in word_dict:
                word_dict[symbol] = set()
            word_dict[symbol].add((row, col))

    # Initially add every occurence as ans
    ans = set()
    for row, col in word_dict[word[0]]:
        ans.add(((row, col), 'r'))
        ans.add(((row, col), 'd'))

    # Remove elements from answer which doesn't follow conditions.
    sym_index = 0
    for symbol in word[1:]:
        sym_index += 1
        ele_to_next_level = set()
        for occur_row, occur_col in word_dict[symbol]:
            for ans_position, direction in ans:
                if (direction is 'r' and ans_position[0] is occur_row and ans_position[1] + sym_index is occur_col) or (direction is 'd' and ans_position[0] + sym_index is occur_row and ans_position[1] is occur_col):
                    ele_to_next_level.add((ans_position, direction))
        ans = ele_to_next_level
    return True if len(ans) > 0 else False




matrix = [
          ['F', 'A', 'C', 'I'],
          ['O', 'B', 'Q', 'P'],
          ['A', 'K', 'O', 'B'],
          ['M', 'A', 'S', 'S']]
print word_search(matrix, 'FOAM')
# True
