#reverse an array

# def swap(arr, index1, index2):
#     arr[index1], arr[index2] = arr[index2], arr[index1]
#     return arr

# def func(arr, i, n):
#     if i >= n/2:
#         return

#     swap(arr, i, n-i-1)
#     func(arr, i + 1, n)
#     return arr

# arr1 = [1, 4, 5, 6, 7]
# new = func(arr1, 0, len(arr1))
# print(new)

#check if a string is palindrome or not

def f(string, i):
    n = len(string)
    if i >= n / 2:
        return True

    if string[i] != string[n - i - 1]:
        return False

    return f(string, i + 1)

print(f("madsm", 0))
