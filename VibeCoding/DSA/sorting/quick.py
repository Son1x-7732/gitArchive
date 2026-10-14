# pick a pivot and place it in its correct place in the sorted array. smaller on the left and
# larger on the right

def quickSort(arr, low, high):
    if low < high:
        pIndex = partition(arr, low, high)
        quickSort(arr, low, pIndex)
        quickSort(arr, pIndex + 1, high)

    
def partition(arr, low, high):
    pivot = arr[low]
    i = low - 1
    j = high + 1

    while True:
        i += 1
        while arr[i] < pivot:
            i += 1
        
        j -= 1
        while arr[j] > pivot:
            j -= 1

        if i >= j:
            return j

        arr[i], arr[j] = arr[j], arr[i]


if __name__ == "__main__":
    array = [5, 4, 3, 2, 1]
    quickSort(array, 0, len(array) - 1)
    print(array)