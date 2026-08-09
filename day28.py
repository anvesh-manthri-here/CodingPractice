# Find the k-th Largest Element in a List
# Given a list, find the k-th largest element in the list.

import random

def place_piviot_in_place(arr, front, end):
    small = front+1
    piviot = arr[front]
    for i in range(front+1, end+1):
        if arr[i] <= piviot:
            arr[i], arr[small] = arr[small], arr[i]
            small += 1
    arr[small-1], arr[front] = arr[front], arr[small-1]
    return small-1


def findKthLargest(arr, front, end, k):
    if front >= end:
        return
    
    piviot = front
    piviot_after_place = place_piviot_in_place(arr, piviot, end)

    if k is piviot_after_place:
        return
    elif k < piviot_after_place:
        findKthLargest(arr, front, piviot-1, k)
    else:
        findKthLargest(arr, piviot+1, end, k)


arr = [3, 5, 2, 4, 6, 9]
k = 3
findKthLargest(arr, 0, len(arr)-1, len(arr) - k)
print arr[len(arr) - k]
# 5


def quick_sort(arr, front, end):
    if front >= end:
        return

    piviot = front
    piviot = place_piviot_in_place(arr, piviot, end)

    quick_sort(arr, front, piviot-1)
    quick_sort(arr, piviot+1, end)


#arr = [3, 5, 2, 4, 4, 6, 8, 5]
#quick_sort(arr, 0, len(arr)-1)
#print arr

