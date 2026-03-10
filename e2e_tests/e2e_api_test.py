"""
E2E API test suite.
Registers a fresh user, logs in, and submits code for 5 different verdicts
(AC, RE, TLE for Python/C++/Java) using the backend API + WebSocket, instead
of a browser.

Routes discovered from backend/server/{main,auth,routes}.py:
  - POST /auth/register   JSON: {username, email, password}
  - POST /auth/login      JSON: {username, password}
  - POST /submit          JSON: {problem_id, language, src_code}, Bearer token
  - WS   /ws/submissions/{id}  -> one JSON message then close
"""

import asyncio
import httpx
import websockets
import json
import uuid

BASE_URL = "http://127.0.0.1:9000"


async def wait_for_verdict(client: httpx.AsyncClient, submission_id: int,
                           token: str, timeout: int = 90) -> dict:
    """Poll GET /submissions/{id} until status is no longer PENDING."""
    headers = {"Authorization": f"Bearer {token}"}
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(f"{BASE_URL}/submissions/{submission_id}",
                             headers=headers)
        if r.status_code == 200:
            data = r.json()
            status = data.get("status", "PENDING")
            if status != "PENDING":
                return data
        await asyncio.sleep(2)
    raise asyncio.TimeoutError(f"Timed out after {timeout}s")


async def test_submission(client: httpx.AsyncClient, token: str,
                          lang: str, code: str, expected_verdict: str):
    print(f"\n{'─'*50}")
    print(f"  Language : {lang}")
    print(f"  Expected : {expected_verdict}")

    # POST /submit
    resp = await client.post(
        f"{BASE_URL}/submit",
        json={"problem_id": 1, "language": lang, "src_code": code},
        headers={"Authorization": f"Bearer {token}"},
    )

    if resp.status_code != 200:
        print(f"  ❌ Submit failed ({resp.status_code}): {resp.text}")
        return False

    submission_id = resp.json()["submission_id"]
    print(f"  Sub ID   : {submission_id} — waiting for verdict …")

    try:
        result = await wait_for_verdict(client, submission_id, token, timeout=90)
    except asyncio.TimeoutError:
        print("  ❌ Timed out waiting for WebSocket verdict")
        return False
    except Exception as exc:
        print(f"  ❌ WS error: {exc}")
        return False

    status    = result.get("status", "UNKNOWN")
    time_ms   = result.get("execution_time_ms", "-")
    mem_mb    = result.get("peak_memory_mb", "-")

    print(f"  Verdict  : {status}  (time={time_ms}ms  mem={mem_mb}MB)")

    if status == expected_verdict:
        print(f"  ✅ PASSED")
        return True
    else:
        print(f"  ❌ FAILED — expected {expected_verdict}, got {status}")
        return False


async def main():
    suffix   = str(uuid.uuid4())[:8]
    username = f"e2e_{suffix}"
    email    = f"e2e_{suffix}@test.com"
    password = "TestPass123!"

    async with httpx.AsyncClient(timeout=15) as client:

        # ── 1. Register ──────────────────────────────────────────────────────
        print(f"\n[1] Registering user: {username}")
        r = await client.post(f"{BASE_URL}/auth/register",
                              json={"username": username,
                                    "email": email,
                                    "password": password})
        if r.status_code not in (200, 201):
            print(f"    ❌ Register failed ({r.status_code}): {r.text}")
            return
        print(f"    ✅ Registered (status={r.status_code})")

        # ── 2. Login ─────────────────────────────────────────────────────────
        print(f"\n[2] Logging in as {username}")
        r = await client.post(f"{BASE_URL}/auth/login",
                              json={"username": username,
                                    "password": password})
        if r.status_code != 200:
            print(f"    ❌ Login failed ({r.status_code}): {r.text}")
            return

        token = r.json()["access_token"]
        print(f"    ✅ Login OK — token obtained")

        # ── 3. Check Problem 1 exists ─────────────────────────────────────────
        print(f"\n[3] Checking problem 1 …")
        r = await client.get(f"{BASE_URL}/problems/1")
        if r.status_code != 200:
            print(f"    ❌ Problem 1 not found ({r.status_code}): {r.text}")
            return
        print(f"    ✅ Problem: {r.json().get('title', '?')}")

        # ── 4. Submission tests ───────────────────────────────────────────────
        print(f"\n[4] Running submission tests …")

        # Helper test codes — problem 1 expects "1 2" on stdout
        tests = [
            # (language, expected_verdict, code)
            # Two Sum in C++ — O(n) hash map
            ("cpp", "AC",
             '#include<iostream>\n#include<vector>\n#include<unordered_map>\nusing namespace std;\n'
             'int main(){\n'
             '    int n; cin>>n;\n'
             '    vector<int> nums(n);\n'
             '    for(int&x:nums) cin>>x;\n'
             '    int target; cin>>target;\n'
             '    unordered_map<int,int> seen;\n'
             '    for(int i=0;i<n;i++){\n'
             '        int comp=target-nums[i];\n'
             '        if(seen.count(comp)){cout<<seen[comp]<<" "<<i<<"\\n";return 0;}\n'
             '        seen[nums[i]]=i;\n'
             '    }\n'
             '    return 0;\n'
             '}'),

            # C++ with nullptr dereference → RE
            ("cpp", "RE",
             '#include<iostream>\nusing namespace std;\n'
             'int main(){int*p=nullptr;*p=42;return 0;}'),

            # Two Sum in Python — O(n) hash map
            ("py", "AC",
             'n = int(input())\nnums = list(map(int, input().split()))\ntarget = int(input())\n'
             'seen = {}\n'
             'for i, v in enumerate(nums):\n'
             '    comp = target - v\n'
             '    if comp in seen:\n'
             '        print(seen[comp], i)\n'
             '        break\n'
             '    seen[v] = i\n'),

            # Infinite loop → TLE
            ("py", "TLE",
             "while True: pass"),

            # Two Sum in Java
            ("java", "AC",
             'import java.util.*;\n'
             'public class Main {\n'
             '    public static void main(String[] args) {\n'
             '        Scanner sc = new Scanner(System.in);\n'
             '        int n = sc.nextInt();\n'
             '        int[] nums = new int[n];\n'
             '        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();\n'
             '        int target = sc.nextInt();\n'
             '        Map<Integer,Integer> seen = new HashMap<>();\n'
             '        for (int i = 0; i < n; i++) {\n'
             '            int comp = target - nums[i];\n'
             '            if (seen.containsKey(comp)) {\n'
             '                System.out.println(seen.get(comp) + " " + i);\n'
             '                return;\n'
             '            }\n'
             '            seen.put(nums[i], i);\n'
             '        }\n'
             '    }\n'
             '}'),
        ]

        passed = 0
        for lang, expected, code in tests:
            ok = await test_submission(client, token, lang, code, expected)
            if ok:
                passed += 1

        print(f"\n{'═'*50}")
        print(f"Results: {passed}/{len(tests)} tests passed")
        print(f"{'═'*50}\n")


if __name__ == "__main__":
    asyncio.run(main())
