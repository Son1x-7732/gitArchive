def max_ones_brute(arr, n):
    max_count = 0
    for i in range(n):
        if arr[i] == 1:
            count = 0
            for j in range(i, n):
                if arr[j] == 1:
                    count += 1
                else:
                    break
            max_count = max(max_count, count)

    return max_count


arr = [1, 1, 0, 1, 1, 1]
print(max_ones_brute(arr, len(arr)))
