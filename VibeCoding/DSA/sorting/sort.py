# selection sort (select minimum and swap at current index)

def selectionSort(arr, n):
    for i in range (n - 1):
        min = i
        for j in range (i + 1, n):
            if arr[j] < arr[min]:
                min = j
        
        arr[i], arr[min] = arr[min], arr[i]

# bubble sort(push the max to the last with adjacent swaps)

def bubbleSort(arr, n):
    for i in range (n-1, 0, -1):
        for j in range (0, i):
            if arr[j] < arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]

#insertion sort(take an element and place it in correct order)
def insertionSort(arr, n):
    for i in range (1, n):
        j = i
        while j > 0 and arr[j - 1] > arr[j]:
            arr[j - 1], arr[j] = arr[j], arr[j - 1]
            j -= 1


#swap
def swap(num1, num2):
    temp = num1
    num1 = num2
    num2 = temp


if __name__ == "__main__":
    array = [5, 4, 3, 2, 1]
    # selectionSort(array, len(array))
    # bubbleSort(array, len(array))
    insertionSort(array, len(array))
    print(array)

