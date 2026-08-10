# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Largest Product of 3 Elements
# From: daily@techseries.dev  |  Sent: 2019-09-27  |  Asked by: Microsoft
#
# You are given an array of integers. Return the largest product that can be made by multiplying any 3 integers in the array.
#
# Example:
# [-4, -4, 2, 8] should return 128 as the largest product can be made by multiplying -4 * -4 * 8 = 128.
#
# def maximum_product_of_three(lst):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d73236be568826

# Largest Product of 3 Elements
# You are given an array of integers. Return the largest product that can be made by multiplying any 3 integers in the array.

def maximum_product_of_three(lst):
    neg1 = None
    neg2 = None
    neg3 = None
    pos1 = None
    pos2 = None
    pos3 = None

    if len(lst) < 3:
        return None
    
    for ele in lst:
        if ele >= 0:
            if not pos1 or ele >= pos1:
                pos3 = pos2
                pos2 = pos1
                pos1 = ele
            elif not pos2 or ele >= pos2:
                pos3 = pos2
                pos2 = ele
            elif not pos3 or ele >= pos3:
                pos3 = ele
        else:
            if not neg1 or neg1 >= ele:
                neg3 = neg2
                neg2 = neg1
                neg1 = ele
            elif not neg2 or neg2 >= ele:
                neg3 = neg2
                neg2 = ele
            elif not neg3 or neg3 >= ele:
                neg3 = ele

    print pos1, pos2, pos3, neg1, neg2, neg3

    if pos1 is not None and pos2 is not None and pos3 is not None:
        if neg1 and neg2 and pos2*pos3 <= neg2*neg1:
            return pos1 * neg1 * neg2
        else:
            return pos1 * pos2 * pos3
    elif pos1 is not None and pos2 is not None:
        if neg1 and neg2 and neg1*neg2 >= pos2:
            return pos1 * neg1 * neg2
        elif neg1:
            return pos1 * pos2 * neg1
        else:
            return None
    elif pos1 is not None:
        if neg1 and neg2:
            return pos1 * neg1 * neg2
        else:
            None
    elif neg1 and neg2 and neg3:
        return neg1*neg2*neg3
    else:
        return None

print maximum_product_of_three([-4, -4, 2, 8])
# 128
print maximum_product_of_three([-4, 0, 2, 8])
# 0

