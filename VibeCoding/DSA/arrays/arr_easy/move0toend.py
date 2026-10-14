arr = [1, 2, 0, 4, 3, 5, 0, 0, 1]

def moveZeroes(arr, n):
    j = 0
    for i in range(n):
        if arr[i] == 0:
            j = i
            break
            
    for i in range(n):
        if arr[i] != 0:
            arr[i], arr[j] = arr[j], arr[i]
            j += 1
            
    return arr
    
print(moveZeroes(arr, len(arr)))