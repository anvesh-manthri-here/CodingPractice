# Falling Dominoes
# Given a string with the initial condition of dominoes, where:
#   . represents that the domino is standing still
#   L represents that the domino is falling to the left side
#   R represents that the domino is falling to the right side
# Figure out the final position of the dominoes. If there are dominoes that get pushed on both ends, the force cancels out and that domino remains upright.

class Solution(object):
    def pushDominoes(self, dominoes):
        left = right = None
        start = 0
        ans = ['.' for i in range(len(dominoes))]

        ind = -1
        for ch in dominoes:
            ind += 1
            if ch is 'L':
                if right is None or start>right:
                    for i in range(start,ind+1):
                        ans[i] = 'L'
                else:
                    left = ind
                    for i in range(right, ((left + right) / 2) + 1):
                        ans[i] = 'R'
                    for i in range(((left + right) / 2) + 1, left + 1):
                        ans[i] = 'L'
                    if (right - left + 1) % 2 is 1:
                        ans[(left + right) / 2] = '.'
                start = ind + 1
            elif ch is 'R':
                if right is not None and start<=right:
                    for i in range(right,ind+1):
                        ans[i] = 'R'
                    start = ind
                right = ind
            else:
                pass

        if right>left:
            for i in range(right, len(dominoes)):
                ans[i] = 'R'
        return "".join(ans)


print Solution().pushDominoes('..R...L..R.')
# ..RR.LL..RR
print Solution().pushDominoes('..R..L..R.')
# ..RRLL..RR
print Solution().pushDominoes('..R...L..L.')
# ..RR.LLLLL.
print Solution().pushDominoes('..R...R..L.')
# ..RRRRRRLL.
