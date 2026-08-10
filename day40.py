# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Look and Say Sequence
# From: daily@techseries.dev  |  Sent: 2019-10-07  |  Asked by: Google
#
# A look-and-say sequence is defined as the integer sequence beginning with a single digit in which the next term is obtained by describing the previous term. An example is easier to understand:
#
# Each consecutive value describes the prior value.
#
# 1      #
# 11     # one 1's
# 21     # two 1's
# 1211   # one 2, and one 1.
# 111221 # one 1, one 2, and two 1's.
#
# Your task is, return the nth term of this sequence.
#
# Original email: https://mail.google.com/mail/u/0/#all/16da6c52c8aa87f2

# Look and Say Sequence
#A look-and-say sequence is defined as the integer sequence beginning with a single digit in which the next term is obtained by describing the previous term. An example is easier to understand:
#Each consecutive value describes the prior value.

1      #
11     # one 1's
21     # two 1's
1211   # one 2, and one 1.
111221 # #one 1, one 2, and two 1's.


def look_and_say(n_term):
    cur = 2
    pterm = '1'
    while cur <= n_term:
        cterm = ''
        ch = pterm[0]
        ch_count = 1
        for c in pterm[1:]:
            if c is ch:
                ch_count += 1
            else:
                cterm += str(ch_count) + str(ch)
                ch = c
                ch_count = 1
        cterm += str(ch_count) + str(ch)
        pterm = cterm
        cur += 1
    return pterm

print look_and_say(10)

