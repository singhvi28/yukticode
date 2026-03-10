import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from Judger.judger import run_judger

test_cases = [
    {"input": "3\n3 2 4\n6\n", "expected_output": "1 2\n"},
]

cpp_code = r"""#include<iostream>
#include<vector>
#include<unordered_map>
using namespace std;
int main(){
    int n; cin>>n;
    vector<int> nums(n);
    for(int&x:nums) cin>>x;
    int target; cin>>target;
    unordered_map<int,int> seen;
    for(int i=0;i<n;i++){
        int comp=target-nums[i];
        if(seen.count(comp)){cout<<seen[comp]<<" "<<i<<"\n";return 0;}
        seen[nums[i]]=i;
    }
    return 0;
}"""

py_code = """n = int(input())
nums = list(map(int, input().split()))
target = int(input())
seen = {}
for i, v in enumerate(nums):
    comp = target - v
    if comp in seen:
        print(seen[comp], i)
        break
    seen[v] = i
"""

print("=== Testing C++ AC ===")
r = run_judger('cpp', 2000, 256, cpp_code, test_cases)
print("Result:", r)

print("\n=== Testing Python AC ===")
r = run_judger('py', 2000, 256, py_code, test_cases)
print("Result:", r)
