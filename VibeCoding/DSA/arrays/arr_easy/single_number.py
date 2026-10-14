def single_number_brute(arr, n):
    for i in range(n):
        count = 0
        for j in range(n):
            if arr[i] == arr[j]:
                count += 1
                
        if count == 1:
            return arr[i]
            
arr = [2, 3, 5, 4, 5, 3, 4]
print(single_number_brute(arr, len(arr)))