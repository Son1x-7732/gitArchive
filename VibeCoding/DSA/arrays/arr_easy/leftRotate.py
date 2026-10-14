arr = [1, 2, 3, 4, 5, 6, 7]

#left rotate by one place
# temp = arr[0]
# for i in range(1, len(arr)):
#     arr[i - 1] = arr[i]

# arr[len(arr) - 1] = temp
# print(arr)

#left rotate by d place(bruteforce)

def leftRotate_brute(arr, n, d):
    d = d % n
    
    temp = []
    for i in range(d):
        temp[i].append(arr[i])
        
    for i in range(d, n):
        arr[i - d] = arr[i]
        
    for i in range(n - d, n):
        arr[i] = temp[i - (n - d)]
        
    return arr
        


#left rotate by d places; d = 2(d mod n) optimal solution
def reverse(arr, start, end):
    while(start <= end):
        temp = arr[start]
        arr[start] = arr[end]
        arr[end] = temp
        start += 1
        end -= 1
    return arr
    
def leftRotate(arr, n, d):
    d = d % n
    
    reverse(arr, 0, d - 1)
    reverse(arr, d, n - 1)
    reverse(arr, 0, n - 1)
    
    return arr
    
print(leftRotate_brute(arr, len(arr), 3))
    