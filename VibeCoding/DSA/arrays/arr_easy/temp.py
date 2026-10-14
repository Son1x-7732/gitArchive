arr = [1, 2, 3, 4, 5]

def reverse(arr, start, end):
    while (start <= end):
        temp = arr[start]
        arr[start] = arr[end]
        arr[end] = temp
        start += 1
        end -= 1
    return arr 
print(reverse(arr, 0, 2))
    