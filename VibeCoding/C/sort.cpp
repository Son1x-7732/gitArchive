#include <iostream>
#include <vector>
using namespace std;

void selectionSort(int arr[], int n) {
    for(int i = 0; i <= n - 2; i++) {
        int min = i;
        for (int j = i + 1; j < n; j++) {
            if (arr[j] < arr[min]) min = j; 
        }

        int temp = arr[min];
        arr[min] = arr[i];
        arr[i] = temp;
    }
}

int main() {
    cout<<"Enter no of integers: " << endl;
    int n;
    cin >> n;
    vector<int> arr(n);
    cout<<"Enter elements of array: " << endl;
    for(int i = 0; i < n; i++) cin >> arr[i];
    selectionSort(arr.data(), n);
    for(int i = 0; i < n; i++) cout << arr[i] << " ";
    cout << endl;
    return 0;
}
