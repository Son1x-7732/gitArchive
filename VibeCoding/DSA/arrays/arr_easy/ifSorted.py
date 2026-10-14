# check if the array is sorted...

arr = [1, 2, 3, 4, 1]


def ifSorted(arr):    
    for i in range(1, len(arr)):
        if arr[i] >= arr[i - 1]:
            continue
        else:
            return False
    return True
    
print(ifSorted(arr))

