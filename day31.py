# Merge Overlapping Intervals
# You are given an array of intervals - that is, an array of tuples (start, end). The array may not be sorted, and could contain overlapping intervals. Return another array where the overlapping intervals are merged.


def place_piviot_in_place(arr, front, end):
    piviot = arr[front]
    small = front + 1

    for i in range(front+1, end+1):
        if arr[i] <= piviot:
            arr[small], arr[i] = arr[i], arr[small]
            small += 1
    arr[front], arr[small-1] = arr[small-1], arr[front]
    return small-1

def quick_sort(arr, front, end):
    if front >= end:
        return

    piviot = place_piviot_in_place(arr, front, end)

    quick_sort(arr, front, piviot-1)
    quick_sort(arr, piviot+1, end)

def merge(intervals):
    quick_sort(intervals, 0, len(intervals) - 1)
    print intervals
    merged_intervel = []
    super_set = (None, None)
    
    for front, end in intervals:
        if super_set[0] is None:
            super_set = (front, end)
        elif front <= super_set[1] and end <= super_set[1]:
            pass
        elif front <= super_set[1] and end >= super_set[1]:
            super_set = (super_set[0] ,end)
        else:
            merged_intervel.append(super_set)
            super_set = (front, end)
    else:
        if super_set[0] is not None:
            merged_intervel.append(super_set)

    return merged_intervel

print merge([(1, 3), (5, 8), (4, 10), (20, 25)])
# [(1, 3), (4, 10), (20, 25)]
print merge([(1, 3), (5, 8), (4, 10), (20, 25), (4, 12)])
# [(1, 3), (4, 12), (20, 25)]
